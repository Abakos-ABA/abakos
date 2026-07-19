// Bridge to the Rust core. All chain RPC/REST + agent calls go through the Rust
// side (net_get / net_post) so the webview never hits CORS on the endpoints.
import { invoke } from "@tauri-apps/api/core";

export const EVM_RPC = "https://evm-rpc.abakos.ai";
export const COSMOS_REST = "https://rest.abakos.ai";
export const AGENT_STATS = "https://explorer.abakos.ai/agent/stats";
export const EXPLORER = "https://abakos.ai/explorer/";
export const DEX = "https://abakos.ai/dex/";
export const EVM_CHAIN_ID = 9721;

export function netGet(url: string): Promise<string> {
  return invoke<string>("net_get", { url });
}
export function netPost(url: string, body: string): Promise<string> {
  return invoke<string>("net_post", { url, body });
}

export function kvGet(key: string): Promise<string | null> {
  return invoke<string | null>("kv_get", { key });
}
export function kvSet(key: string, value: string): Promise<void> {
  return invoke<void>("kv_set", { key, value });
}
export function kvDelete(key: string): Promise<void> {
  return invoke<void>("kv_delete", { key });
}

export interface HardwareInfo {
  os: string;
  arch: string;
  cpu_threads: number;
  has_nvidia: boolean;
}
export function hardwareInfo(): Promise<HardwareInfo> {
  return invoke<HardwareInfo>("hardware_info");
}

export interface MinerStatus {
  state: "stopped" | "starting" | "running" | "error";
  error: string | null;
  address: string | null;
  pool: string;
  cpu_running: boolean;
  gpu_running: boolean;
  cpu_hashrate: number; // RandomX / Monero
  gpu_hashrate: number; // PearlHash / Pearl
  shares_good: number;
  shares_total: number;
  gpu_shares_good: number;
}
export function enableMining(): Promise<string> {
  return invoke<string>("enable_mining");
}
export function startMiner(address: string, threads: number, cpu: boolean, gpu: boolean): Promise<void> {
  return invoke<void>("start_miner", { address, threads, cpu, gpu });
}
export function stopMiner(): Promise<void> {
  return invoke<void>("stop_miner");
}
export function minerStatus(): Promise<MinerStatus> {
  return invoke<MinerStatus>("miner_status");
}

let rpcId = 1;
export async function rpc<T = unknown>(method: string, params: unknown[]): Promise<T> {
  const body = JSON.stringify({ jsonrpc: "2.0", id: rpcId++, method, params });
  const text = await netPost(EVM_RPC, body);
  const json = JSON.parse(text);
  if (json.error) throw new Error(json.error.message || JSON.stringify(json.error));
  return json.result as T;
}

/** Native ABA balance (18-dec on the EVM) as a decimal number. */
export async function evmBalanceAba(addr0x: string): Promise<number> {
  const hex = await rpc<string>("eth_getBalance", [addr0x, "latest"]);
  return Number(BigInt(hex)) / 1e18;
}

export async function gasPrice(): Promise<bigint> {
  const hex = await rpc<string>("eth_gasPrice", []);
  return BigInt(hex);
}

export async function nonce(addr0x: string): Promise<number> {
  const hex = await rpc<string>("eth_getTransactionCount", [addr0x, "pending"]);
  return Number(BigInt(hex));
}

export async function sendRawTx(rawHex: string): Promise<string> {
  return rpc<string>("eth_sendRawTransaction", [rawHex]);
}

export interface ProviderStat {
  address: string;
  cpu_hs: number;
  gpu_hs: number;
  cpu_coin: string | null;
  gpu_coin: string | null;
  earned_aba: number;
  share_hs: number;
  window_shares: number;
  share_fraction: number;
  last_seen_s: number;
  active: boolean;
}
export interface AgentStats {
  running: boolean;
  epoch: number;
  aba_price_usd: number;
  aba_price_source: string;
  payout_basis?: { source: string; window_total_shares: number; providers_paid: number };
  oracle?: { cpu?: { coin: string; tag: string; algorithm: string }; gpu?: { coin: string; tag: string } };
  providers?: ProviderStat[];
}
export async function agentStats(): Promise<AgentStats> {
  const text = await netGet(AGENT_STATS);
  return JSON.parse(text) as AgentStats;
}

export function findProvider(stats: AgentStats, address: string): ProviderStat | undefined {
  return (stats.providers || []).find((p) => p.address === address);
}
