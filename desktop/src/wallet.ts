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
  cosmosBalanceAba,
  faucetRequest,
  gasPrice,
  nonce,
  sendRawTx,
  EVM_CHAIN_ID,
} from "./net";

const K_KEYSTORE = "keystore";
const K_ADDR = "address0x";
const K_MNEMONIC = "mnemonic_enc";
const K_BOOK = "addressbook";

export interface Addresses {
  evm: string;
  aba: string;
}

export interface Contact {
  name: string;
  addr: string;
}

// --- password-based encryption for the recovery phrase (Web Crypto) -----------
function b64(buf: ArrayBufferLike): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf)));
}
function unb64(s: string): Uint8Array {
  return Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
}
async function deriveKey(password: string, salt: BufferSource): Promise<CryptoKey> {
  const base = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password) as unknown as BufferSource,
    "PBKDF2",
    false,
    ["deriveKey"],
  );
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations: 200000, hash: "SHA-256" },
    base,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}
async function encryptText(text: string, password: string): Promise<string> {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await deriveKey(password, salt as unknown as BufferSource);
  const ct = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: iv as unknown as BufferSource },
    key,
    new TextEncoder().encode(text) as unknown as BufferSource,
  );
  return JSON.stringify({ v: 1, salt: b64(salt.buffer), iv: b64(iv.buffer), ct: b64(ct) });
}
async function decryptText(blob: string, password: string): Promise<string> {
  const o = JSON.parse(blob) as { salt: string; iv: string; ct: string };
  const key = await deriveKey(password, unb64(o.salt) as unknown as BufferSource);
  const pt = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: unb64(o.iv) as unknown as BufferSource },
    key,
    unb64(o.ct) as unknown as BufferSource,
  );
  return new TextDecoder().decode(pt);
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

async function persist(w: Wallet | HDNodeWallet, password: string, mnemonic?: string): Promise<void> {
  // Portable keystore for the private key; the recovery phrase (if any) is stored
  // as a separate password-encrypted blob so it can be re-shown later.
  const plain = new Wallet(w.privateKey);
  const keystore = await plain.encrypt(password);
  await kvSet(K_KEYSTORE, keystore);
  await kvSet(K_ADDR, w.address);
  if (mnemonic) await kvSet(K_MNEMONIC, await encryptText(mnemonic, password));
  else await kvDelete(K_MNEMONIC);
  signer = plain;
  addr0x = w.address;
}

/** Create a brand-new wallet. Returns the mnemonic ONCE for the user to back up. */
export async function createNew(password: string): Promise<{ mnemonic: string; addresses: Addresses }> {
  const w = Wallet.createRandom();
  const mnemonic = w.mnemonic?.phrase ?? "";
  await persist(w, password, mnemonic);
  return { mnemonic, addresses: addressesFrom(w.address) };
}

export async function importMnemonic(phrase: string, password: string): Promise<Addresses> {
  const w = HDNodeWallet.fromPhrase(phrase.trim());
  await persist(w, password, phrase.trim());
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
  await kvDelete(K_MNEMONIC);
}

export async function balanceAba(): Promise<number> {
  const a = addr0x ?? (await kvGet(K_ADDR));
  if (!a) throw new Error("no address");
  return evmBalanceAba(a);
}

/** Cosmos-side bank balance (uaba, 6-dec) via REST. Same account as the EVM one. */
export async function balanceCosmos(): Promise<number> {
  const a = currentAddresses();
  if (!a) throw new Error("no address");
  return cosmosBalanceAba(a.aba);
}

export async function faucet(): Promise<string> {
  const a = currentAddresses();
  if (!a) throw new Error("no address");
  return faucetRequest(a.aba);
}

/** Export the raw private key (0x). Re-verifies the password against the keystore. */
export async function exportPrivateKey(password: string): Promise<string> {
  const keystore = await kvGet(K_KEYSTORE);
  if (!keystore) throw new Error("no wallet");
  const w = await Wallet.fromEncryptedJson(keystore, password);
  return w.privateKey;
}

export async function hasMnemonic(): Promise<boolean> {
  return (await kvGet(K_MNEMONIC)) != null;
}

/** Reveal the recovery phrase (only if the wallet was created/imported from one). */
export async function exportMnemonic(password: string): Promise<string> {
  const blob = await kvGet(K_MNEMONIC);
  if (!blob) throw new Error("no recovery phrase stored (this wallet was imported by private key)");
  return decryptText(blob, password);
}

// --- address book -------------------------------------------------------------
export async function getContacts(): Promise<Contact[]> {
  const s = await kvGet(K_BOOK);
  try {
    return s ? (JSON.parse(s) as Contact[]) : [];
  } catch {
    return [];
  }
}
export async function addContact(name: string, addr: string): Promise<void> {
  const book = await getContacts();
  book.push({ name: name.trim(), addr: addr.trim() });
  await kvSet(K_BOOK, JSON.stringify(book));
}
export async function removeContact(index: number): Promise<void> {
  const book = await getContacts();
  book.splice(index, 1);
  await kvSet(K_BOOK, JSON.stringify(book));
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
