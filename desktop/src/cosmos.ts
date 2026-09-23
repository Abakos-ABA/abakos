// Cosmos-SDK transaction signing for the EVM-only wallet.
//
// The Abakos wallet is an Ethereum key (secp256k1, coinType 60); its on-chain
// account is a cosmos/evm account whose pubkey type is
// `/cosmos.evm.crypto.v1.ethsecp256k1.PubKey`. Native EVM transfers go out as
// EVM txs (wallet.ts sendAba). But a `DepositAuthorization` grant - the thing
// that lets your wallet sponsor a compute provider's bid deposits with a spend
// cap - is a Cosmos-SDK authz message and cannot ride an EVM tx.
//
// So we build a SIGN_MODE_DIRECT Cosmos tx by hand (no cosmjs/protobufjs - the
// app carries only ethers). The one crypto subtlety: ethsecp256k1 verifies the
// signature over `keccak256(SignDoc)` with a 64-byte [R||S] signature (see
// cosmos/evm crypto/ethsecp256k1.go: VerifySignature -> crypto.VerifySignature(
// key, Keccak256(msg), sig)). ethers' SigningKey.sign() signs exactly a 32-byte
// digest, so we hand it keccak256(SignDoc) and take r||s.
//
// Proto field numbers below are verified against chain-sdk:
//   DepositAuthorization  chain-sdk/go/node/escrow/v1/authz.pb.go:74,78,82
//     spend_limit(1,Coin, deprecated must be zero) scopes(2,packed enum) spend_limits(3,repeated Coin)
//   scope bid = 2 (authz.pb.go:41); type url /akash.escrow.v1.DepositAuthorization
//   revoke msg type url = /akash.escrow.v1.MsgAccountDeposit (authz.go:43-45)
import { keccak256, getBytes } from "ethers";
import { COSMOS_REST, COSMOS_CHAIN_ID, netGet, netPost } from "./net";

const DEPOSIT_AUTHZ_TYPE = "/akash.escrow.v1.DepositAuthorization";
const DEPOSIT_MSG_TYPE = "/akash.escrow.v1.MsgAccountDeposit";
const PUBKEY_TYPE = "/cosmos.evm.crypto.v1.ethsecp256k1.PubKey";
const SCOPE_BID = 2;
const SIGN_MODE_DIRECT = 1;
const DENOM = "uaba";

/** Signs a 32-byte digest, returns the 64-byte [R||S] cosmos signature. */
export type SignDigest = (digest: Uint8Array) => Uint8Array;

// --- minimal protobuf writer (proto3 wire format) -----------------------------
class W {
  private parts: number[] = [];
  private varint(n: bigint): void {
    let v = n;
    do {
      let b = Number(v & 0x7fn);
      v >>= 7n;
      if (v > 0n) b |= 0x80;
      this.parts.push(b);
    } while (v > 0n);
  }
  private tag(field: number, wire: number): void {
    this.varint(BigInt((field << 3) | wire));
  }
  /** length-delimited (wire 2): embedded message / bytes / string. */
  ld(field: number, data: Uint8Array): this {
    this.tag(field, 2);
    this.varint(BigInt(data.length));
    for (const b of data) this.parts.push(b);
    return this;
  }
  str(field: number, s: string): this {
    if (!s) return this; // proto3 scalar default is omitted
    return this.ld(field, new TextEncoder().encode(s));
  }
  /** varint scalar (uint64 / enum). Zero is omitted (proto3 default). */
  uint(field: number, n: bigint): this {
    if (n === 0n) return this;
    this.tag(field, 0);
    this.varint(n);
    return this;
  }
  bytes(): Uint8Array {
    return Uint8Array.from(this.parts);
  }
}

/** packed repeated varint payload, e.g. scopes [2]. */
function packedVarints(vals: number[]): Uint8Array {
  const out: number[] = [];
  for (const val of vals) {
    let v = BigInt(val);
    do {
      let b = Number(v & 0x7fn);
      v >>= 7n;
      if (v > 0n) b |= 0x80;
      out.push(b);
    } while (v > 0n);
  }
  return Uint8Array.from(out);
}

function coin(denom: string, amount: string): Uint8Array {
  // Coin { denom(1,string) amount(2,string) }; amount is a decimal string ("0" is non-default -> emitted)
  return new W().ld(1, new TextEncoder().encode(denom)).ld(2, new TextEncoder().encode(amount)).bytes();
}

function any(typeUrl: string, value: Uint8Array): Uint8Array {
  return new W().str(1, typeUrl).ld(2, value).bytes();
}

// --- messages -----------------------------------------------------------------
function depositAuthorization(spendLimitUaba: string): Uint8Array {
  // spend_limit(1) MUST be a zero coin uaba/0 (NOT omitted) - the chain's re-credit
  // path reads SpendLimit.Amount.GT(0) without a nil-guard (keeper.go:1066), so a
  // missing/nil amount would panic. Zero is valid (authz.go:151-159).
  return new W()
    .ld(1, coin(DENOM, "0"))
    .ld(2, packedVarints([SCOPE_BID]))
    .ld(3, coin(DENOM, spendLimitUaba))
    .bytes();
}

/** MsgGrant Any: sponsor `grantee`'s bid deposits from `granter`, capped at spendLimitUaba. */
export function msgGrantDeposit(granter: string, grantee: string, spendLimitUaba: string): Uint8Array {
  const authAny = any(DEPOSIT_AUTHZ_TYPE, depositAuthorization(spendLimitUaba));
  const grant = new W().ld(1, authAny).bytes(); // Grant { authorization(1,Any); expiration(2) omitted = no expiry }
  const msg = new W().str(1, granter).str(2, grantee).ld(3, grant).bytes();
  return any("/cosmos.authz.v1beta1.MsgGrant", msg);
}

/** MsgRevoke Any: kill-switch - revoke the deposit authorization. */
export function msgRevokeDeposit(granter: string, grantee: string): Uint8Array {
  const msg = new W().str(1, granter).str(2, grantee).str(3, DEPOSIT_MSG_TYPE).bytes();
  return any("/cosmos.authz.v1beta1.MsgRevoke", msg);
}

// --- tx assembly + broadcast --------------------------------------------------
function pubKeyAny(compressed: Uint8Array): Uint8Array {
  const pk = new W().ld(1, compressed).bytes(); // PubKey { key(1,bytes) }
  return any(PUBKEY_TYPE, pk);
}

function b64(bytes: Uint8Array): string {
  let s = "";
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s);
}

interface Account {
  accountNumber: bigint;
  sequence: bigint;
}

async function fetchAccount(aba: string): Promise<Account> {
  const text = await netGet(`${COSMOS_REST}/cosmos/auth/v1beta1/accounts/${aba}`);
  const a = (JSON.parse(text).account ?? {}) as Record<string, unknown>;
  const base = (a.base_account ?? a) as Record<string, unknown>; // BaseAccount, or EthAccount-wrapped
  return {
    accountNumber: BigInt(String(base.account_number ?? "0")),
    sequence: BigInt(String(base.sequence ?? "0")),
  };
}

interface SignAndBroadcast {
  granterAba: string;
  pubKeyCompressed: Uint8Array;
  msgs: Uint8Array[];
  sign: SignDigest;
  gasLimit?: bigint;
}

async function signAndBroadcast(o: SignAndBroadcast): Promise<string> {
  const { accountNumber, sequence } = await fetchAccount(o.granterAba);

  const bodyW = new W();
  for (const m of o.msgs) bodyW.ld(1, m); // TxBody.messages(1, repeated Any)
  const body = bodyW.bytes();

  const single = new W().uint(1, BigInt(SIGN_MODE_DIRECT)).bytes(); // ModeInfo.Single { mode(1) }
  const modeInfo = new W().ld(1, single).bytes(); // ModeInfo { single(1) }
  const signerInfo = new W()
    .ld(1, pubKeyAny(o.pubKeyCompressed)) // public_key(1,Any)
    .ld(2, modeInfo) // mode_info(2)
    .uint(3, sequence) // sequence(3)
    .bytes();
  const fee = new W().uint(2, o.gasLimit ?? 300000n).bytes(); // Fee { amount(1) empty; gas_limit(2) } - 0-fee chain
  const authInfo = new W().ld(1, signerInfo).ld(2, fee).bytes();

  const signDoc = new W()
    .ld(1, body) // body_bytes
    .ld(2, authInfo) // auth_info_bytes
    .str(3, COSMOS_CHAIN_ID) // chain_id
    .uint(4, accountNumber) // account_number
    .bytes();

  const sig = o.sign(getBytes(keccak256(signDoc))); // ethsecp256k1: sign over keccak256(SignDoc)
  if (sig.length !== 64) throw new Error(`bad signature length ${sig.length}`);

  const txRaw = new W().ld(1, body).ld(2, authInfo).ld(3, sig).bytes(); // TxRaw
  const resp = await netPost(
    `${COSMOS_REST}/cosmos/tx/v1beta1/txs`,
    JSON.stringify({ tx_bytes: b64(txRaw), mode: "BROADCAST_MODE_SYNC" }),
  );
  const r = (JSON.parse(resp).tx_response ?? {}) as { code?: number; txhash?: string; raw_log?: string };
  if (r.code && r.code !== 0) throw new Error(r.raw_log || `tx rejected (code ${r.code})`);
  return String(r.txhash ?? "");
}

// --- public API ---------------------------------------------------------------
/** uaba (6-dec integer string) from an ABA number. */
export function toUaba(aba: number): string {
  return Math.round(aba * 1e6).toString();
}

export interface GrantOpts {
  granterAba: string;
  granteeAba: string;
  pubKeyCompressed: Uint8Array;
  sign: SignDigest;
}

/** Sign+broadcast a DepositAuthorization grant (activate hosting sponsorship). */
export function grantHostingSponsor(o: GrantOpts & { maxAba: number }): Promise<string> {
  const msg = msgGrantDeposit(o.granterAba, o.granteeAba, toUaba(o.maxAba));
  return signAndBroadcast({ granterAba: o.granterAba, pubKeyCompressed: o.pubKeyCompressed, msgs: [msg], sign: o.sign });
}

/** Sign+broadcast a revoke (kill-switch). */
export function revokeHostingSponsor(o: GrantOpts): Promise<string> {
  const msg = msgRevokeDeposit(o.granterAba, o.granteeAba);
  return signAndBroadcast({ granterAba: o.granterAba, pubKeyCompressed: o.pubKeyCompressed, msgs: [msg], sign: o.sign });
}

/** Read the current deposit-authorization spend limit (uaba) this granter gave the grantee, or null. */
export async function fetchDepositGrant(granterAba: string, granteeAba: string): Promise<{ spendLimitUaba: string } | null> {
  try {
    const text = await netGet(
      `${COSMOS_REST}/cosmos/authz/v1beta1/grants?granter=${granterAba}&grantee=${granteeAba}`,
    );
    const grants = (JSON.parse(text).grants ?? []) as { authorization?: Record<string, unknown> }[];
    for (const g of grants) {
      const a = g.authorization ?? {};
      if (String(a["@type"] ?? "").endsWith("DepositAuthorization")) {
        const limits = (a.spend_limits as { denom: string; amount: string }[] | undefined) ?? [];
        const uaba = limits.find((c) => c.denom === DENOM);
        return { spendLimitUaba: uaba ? String(uaba.amount) : "0" };
      }
    }
    return null;
  } catch {
    return null;
  }
}
