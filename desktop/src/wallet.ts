// Self-custody ABA wallet. Uses eth-style key derivation (coinType 60): the 0x
// address and its bech32 form (abakos1) are the same account on the Abakos EVM.
// The key is stored as a password-encrypted keystore (scrypt) via the Rust KV.
import { Wallet, HDNodeWallet, parseEther } from "ethers";
import { ethToAbakos, abakosToEth } from "./bech32";
import {
  kvGet,
  kvSet,
  kvDelete,
  evmBalanceAba,
  gasPrice,
  nonce,
  sendRawTx,
  EVM_CHAIN_ID,
} from "./net";

const K_KEYSTORE = "keystore";
const K_ADDR = "address0x";

export interface Addresses {
  evm: string;
  aba: string;
}

let signer: Wallet | HDNodeWallet | null = null;
let addr0x: string | null = null;

export function addressesFrom(evm: string): Addresses {
  return { evm, aba: ethToAbakos(evm) };
}

export async function hasWallet(): Promise<boolean> {
  return (await kvGet(K_KEYSTORE)) != null;
}

/** Address is cached in the KV so it can be shown before unlocking. */
export async function storedAddresses(): Promise<Addresses | null> {
  const evm = addr0x ?? (await kvGet(K_ADDR));
  return evm ? addressesFrom(evm) : null;
}

export function isUnlocked(): boolean {
  return signer != null;
}

export function currentAddresses(): Addresses | null {
  return addr0x ? addressesFrom(addr0x) : null;
}

async function persist(w: Wallet | HDNodeWallet, password: string): Promise<void> {
  // Encrypt just the private key (portable keystore, not the mnemonic).
  const plain = new Wallet(w.privateKey);
  const keystore = await plain.encrypt(password);
  await kvSet(K_KEYSTORE, keystore);
  await kvSet(K_ADDR, w.address);
  signer = plain;
  addr0x = w.address;
}

/** Create a brand-new wallet. Returns the mnemonic ONCE for the user to back up. */
export async function createNew(password: string): Promise<{ mnemonic: string; addresses: Addresses }> {
  const w = Wallet.createRandom();
  const mnemonic = w.mnemonic?.phrase ?? "";
  await persist(w, password);
  return { mnemonic, addresses: addressesFrom(w.address) };
}

export async function importMnemonic(phrase: string, password: string): Promise<Addresses> {
  const w = HDNodeWallet.fromPhrase(phrase.trim());
  await persist(w, password);
  return addressesFrom(w.address);
}

export async function importPrivateKey(pk: string, password: string): Promise<Addresses> {
  const clean = pk.trim().startsWith("0x") ? pk.trim() : "0x" + pk.trim();
  const w = new Wallet(clean);
  await persist(w, password);
  return addressesFrom(w.address);
}

export async function unlock(password: string): Promise<Addresses> {
  const keystore = await kvGet(K_KEYSTORE);
  if (!keystore) throw new Error("no wallet to unlock");
  const w = await Wallet.fromEncryptedJson(keystore, password);
  signer = w as Wallet | HDNodeWallet;
  addr0x = w.address;
  return addressesFrom(w.address);
}

export function lock(): void {
  signer = null;
}

export async function forget(): Promise<void> {
  signer = null;
  addr0x = null;
  await kvDelete(K_KEYSTORE);
  await kvDelete(K_ADDR);
}

export async function balanceAba(): Promise<number> {
  const a = addr0x ?? (await kvGet(K_ADDR));
  if (!a) throw new Error("no address");
  return evmBalanceAba(a);
}

/** Send native ABA on the EVM. `to` may be a 0x or abakos1 address. Zero-fee chain. */
export async function sendAba(to: string, amountAba: string): Promise<string> {
  if (!signer || !addr0x) throw new Error("wallet locked");
  let to0x = to.trim();
  if (to0x.startsWith("abakos1")) to0x = abakosToEth(to0x);
  if (!/^0x[0-9a-fA-F]{40}$/.test(to0x)) throw new Error("recipient must be a 0x or abakos1 address");
  const value = parseEther(amountAba);
  const gp = await gasPrice();
  const tx = {
    to: to0x,
    value,
    nonce: await nonce(addr0x),
    gasLimit: 21000n,
    gasPrice: gp,
    chainId: EVM_CHAIN_ID,
    type: 0,
  };
  const raw = await signer.signTransaction(tx);
  return sendRawTx(raw);
}
