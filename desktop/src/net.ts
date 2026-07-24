// Bridge to the Rust core. All chain RPC/REST + agent calls go through the Rust
// side (net_get / net_post) so the webview never hits CORS on the endpoints.
import { invoke } from "@tauri-apps/api/core";

export const EVM_RPC = "https://evm-rpc.abakos.ai";
export const COSMOS_REST = "https://rest.abakos.ai";
export const AGENT_STATS = "https://explorer.abakos.ai/agent/stats";
export const AGENT_REPORT = "https://explorer.abakos.ai/agent/report";
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

export interface HostProviderStatus {
  state: "stopped" | "starting" | "running" | "error" | "unavailable" | string;
  error: string | null;
  host_uri: string | null;
  unit: string;
  platform_ok: boolean;
}
export function startProvider(): Promise<void> {
  return invoke<void>("start_provider");
}
export function stopProvider(): Promise<void> {
  return invoke<void>("stop_provider");
}
export function providerDaemonStatus(): Promise<HostProviderStatus> {
  return invoke<HostProviderStatus>("provider_status");
}

/** On-chain provider registration (host_uri + attributes). */
export async function chainProvider(owner: string): Promise<{ host_uri: string; owner: string } | null> {
  try {
    const text = await netGet(`${COSMOS_REST}/akash/provider/v1beta4/providers/${owner}`);
    const j = JSON.parse(text);
    const p = j.provider;
    if (!p?.host_uri) return null;
    return { host_uri: String(p.host_uri), owner: String(p.owner || owner) };
  } catch {
    return null;
  }
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

/** Cosmos bank balance (uaba, 6-dec) as a decimal number, via REST. */
export async function cosmosBalanceAba(aba: string): Promise<number> {
  const text = await netGet(`${COSMOS_REST}/cosmos/bank/v1beta1/balances/${aba}`);
  const j = JSON.parse(text);
  const c = (j.balances || []).find((b: { denom: string }) => b.denom === "uaba");
  return c ? Number(c.amount) / 1e6 : 0;
}

/** Request test ABA from the sandbox faucet. Returns the tx hash on success. */
export async function faucetRequest(aba: string): Promise<string> {
  const text = await netPost("https://explorer.abakos.ai/faucet", JSON.stringify({ address: aba }));
  const j = JSON.parse(text);
  if (j.ok) return j.txhash as string;
  throw new Error(j.error || "faucet failed" + (j.retry_after_s ? ` (retry in ${j.retry_after_s}s)` : ""));
}

export interface TxInfo {
  hash: string;
  height: number;
  ts?: string;
  ok: boolean;
  label: string;
  direction: "in" | "out" | "none";
  amountAba: number;
  /** Pre-formatted amount for non-ABA flows (e.g. "0.2 USDC (IBC)"). Wins over amountAba. */
  amountText?: string;
  counterparty?: string;
  /** Which watched account this row belongs to ("provider" rows get a badge). */
  account?: "wallet" | "provider";
}

/** Known IBC denom hashes on abakos-sandbox-1 (USDC via the Noble channel). */
const IBC_DENOMS: Record<string, { sym: string; dec: number }> = {
  "ibc/8E27BA2D5493AF5636760E354E46004562C46AB7EC0CC4C1CA14E9E20E2545B5": { sym: "USDC", dec: 6 },
};

const TYPE_LABELS: Record<string, string> = {
  MsgEthereumTx: "EVM transfer",
  MsgCreateClient: "IBC · Create client",
  MsgUpdateClient: "IBC · Update client",
  MsgConnectionOpenInit: "IBC · Connection init",
  MsgConnectionOpenAck: "IBC · Connection ack",
  MsgConnectionOpenTry: "IBC · Connection try",
  MsgConnectionOpenConfirm: "IBC · Connection confirm",
  MsgChannelOpenInit: "IBC · Channel init",
  MsgChannelOpenTry: "IBC · Channel try",
  MsgChannelOpenAck: "IBC · Channel ack",
  MsgChannelOpenConfirm: "IBC · Channel confirm",
  MsgRecvPacket: "IBC · Receive",
  MsgAcknowledgement: "IBC · Acknowledge",
  MsgTimeout: "IBC · Timeout",
  MsgTransfer: "IBC · Transfer",
};

/** "MsgCreateDeployment" -> "Create deployment". */
function msgLabel(typeUrl: string): string {
  const raw = typeUrl.split(".").pop() || typeUrl;
  if (TYPE_LABELS[raw]) return TYPE_LABELS[raw];
  const name = raw.replace(/^Msg/, "");
  const words = name.replace(/([a-z0-9])([A-Z])/g, "$1 $2").toLowerCase();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : typeUrl;
}

/** Format a non-ABA coin (uusdc / ibc-hash) for display; null when unknown. */
function fmtForeign(amount: string, denom: string): string | null {
  if (denom === "uusdc") return `${Number(amount) / 1e6} USDC`;
  const known = IBC_DENOMS[denom];
  if (known) return `${Number(amount) / Math.pow(10, known.dec)} ${known.sym} (IBC)`;
  if (denom.startsWith("ibc/")) return `${Number(amount) / 1e6} ${denom.slice(0, 10)}… (IBC)`;
  return null;
}

/** Sum the uaba part of a coin string like "5000000uaba" or "1uaba,2ufoo". */
function parseUaba(s: string): number {
  let total = 0;
  for (const part of String(s || "").split(",")) {
    const m = part.trim().match(/^(\d+)uaba$/);
    if (m) total += Number(m[1]);
  }
  return total;
}

interface RawTxResponse {
  txhash: string;
  height: string;
  timestamp?: string;
  code: number;
  events?: { type: string; attributes?: { key: string; value: string }[] }[];
  tx?: { body?: { messages?: Record<string, unknown>[] } };
}

function decodeTx(t: RawTxResponse, aba: string): TxInfo {
  // Direction + net amount from the tx's indexed transfer events — accurate for
  // bank sends, faucet drops, escrow deposits and refunds alike.
  let inU = 0;
  let outU = 0;
  let cpIn: string | undefined;
  let cpOut: string | undefined;
  let foreign: { text: string; dir: "in" | "out" } | undefined;
  for (const ev of t.events || []) {
    if (ev.type !== "transfer") continue;
    let rec = "";
    let snd = "";
    for (const at of ev.attributes || []) {
      if (at.key === "recipient") rec = at.value;
      else if (at.key === "sender") snd = at.value;
      else if (at.key === "amount") {
        const mine = rec === aba && snd !== aba ? "in" : snd === aba && rec !== aba ? "out" : null;
        if (mine) {
          const amt = parseUaba(at.value);
          if (mine === "in") {
            inU += amt;
            if (snd) cpIn = cpIn || snd;
          } else {
            outU += amt;
            if (rec) cpOut = cpOut || rec;
          }
          // Non-ABA flows (IBC-USDC etc.) don't sum into uaba; keep the first one for display.
          if (!amt && !foreign) {
            for (const part of at.value.split(",")) {
              const m = part.trim().match(/^(\d+)(.+)$/);
              const txt = m ? fmtForeign(m[1], m[2]) : null;
              if (txt) {
                foreign = { text: txt, dir: mine };
                break;
              }
            }
          }
        }
        rec = snd = "";
      }
    }
  }

  const msgs = t.tx?.body?.messages || [];
  // Relayer txs pair UpdateClient with the actual packet — label the packet.
  const first = (msgs.find(m => /MsgRecvPacket|MsgAcknowledgement|MsgTransfer|MsgTimeout|MsgEthereumTx/.test(String(m["@type"]))) ||
    msgs[0] ||
    {}) as Record<string, unknown>;
  const typeUrl = String(first["@type"] || "");
  let label = msgLabel(typeUrl || "Tx");
  let amountAba = Math.abs(inU - outU) / 1e6;
  let direction: TxInfo["direction"] = inU > outU ? "in" : outU > inU ? "out" : "none";
  let counterparty = direction === "in" ? cpIn : cpOut;

  if (typeUrl.endsWith("bank.v1beta1.MsgSend")) {
    const from = String(first.from_address || "");
    const to = String(first.to_address || "");
    direction = from === aba ? "out" : "in";
    label = direction === "out" ? "Send" : "Receive";
    counterparty = direction === "out" ? to : from;
    if (!amountAba) {
      amountAba = parseUaba(
        ((first.amount as { denom: string; amount: string }[]) || [])
          .map((c) => `${c.amount}${c.denom}`)
          .join(","),
      ) / 1e6;
    }
  } else if (typeUrl.endsWith("MsgEthereumTx")) {
    // EVM value is 18-dec inside the inner tx data.
    label = "EVM transfer";
    const data = (first.data || {}) as Record<string, unknown>;
    const wei = Number(String(data.value || "0"));
    if (!amountAba && Number.isFinite(wei)) amountAba = wei / 1e18;
    if (!counterparty && data.to) counterparty = String(data.to);
    if (direction === "none") direction = "out";
  }
  if (msgs.length > 1 && !typeUrl.includes("ibc.")) label += ` +${msgs.length - 1}`;

  let amountText: string | undefined;
  if (!amountAba && foreign) {
    amountText = foreign.text;
    if (direction === "none") direction = foreign.dir;
  }

  return {
    hash: t.txhash,
    height: Number(t.height),
    ts: t.timestamp,
    ok: t.code === 0,
    label,
    direction,
    amountAba,
    amountText,
    counterparty,
  };
}

/**
 * Transaction history for an address via Cosmos REST tx search: everything the
 * account signed plus everything it received, merged and decoded. Best-effort —
 * returns [] if the indexer is unavailable.
 */
export async function fetchTxs(aba: string, limit = 30): Promise<TxInfo[]> {
  const queries = [`message.sender='${aba}'`, `transfer.recipient='${aba}'`];
  const lists = await Promise.all(
    queries.map(async (q) => {
      try {
        const url = `${COSMOS_REST}/cosmos/tx/v1beta1/txs?query=${encodeURIComponent(q)}&order_by=2&limit=${limit}`;
        return (JSON.parse(await netGet(url)).tx_responses || []) as RawTxResponse[];
      } catch {
        return [] as RawTxResponse[];
      }
    }),
  );
  const seen = new Set<string>();
  const out: TxInfo[] = [];
  for (const t of lists.flat()) {
    if (seen.has(t.txhash)) continue;
    seen.add(t.txhash);
    out.push(decodeTx(t, aba));
  }
  out.sort((x, y) => y.height - x.height);
  return out;
}

/**
 * Wallet history plus (optionally) the linked provider account's history, merged
 * and tagged. A tx touching both accounts keeps the wallet perspective.
 */
export async function fetchTxsWithProvider(aba: string, providerAddr: string | null, limit = 30): Promise<TxInfo[]> {
  const [mine, prov] = await Promise.all([
    fetchTxs(aba, limit),
    providerAddr && providerAddr !== aba ? fetchTxs(providerAddr, limit) : Promise.resolve([] as TxInfo[]),
  ]);
  const seen = new Set(mine.map((t) => t.hash));
  const out: TxInfo[] = mine.map((t) => ({ ...t, account: "wallet" }));
  for (const t of prov) {
    if (seen.has(t.hash)) continue;
    out.push({ ...t, account: "provider" });
  }
  out.sort((x, y) => y.height - x.height);
  return out;
}

/** Providers registered on chain (the sandbox has exactly one). */
export async function chainProviders(): Promise<{ owner: string; host_uri: string }[]> {
  try {
    const text = await netGet(`${COSMOS_REST}/akash/provider/v1beta4/providers?pagination.limit=50`);
    return (JSON.parse(text).providers || []).map((p: { owner: string; host_uri: string }) => ({
      owner: String(p.owner),
      host_uri: String(p.host_uri),
    }));
  } catch {
    return [];
  }
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

export interface MinerReport {
  address: string;
  cpu_hashrate_hs: number;
  gpu_hashrate_hs: number;
  cpu_coin?: string;
  gpu_coin?: string;
  miner?: string;
  os?: string;
}
/**
 * Report this rig's live CPU+GPU hashrate to the agent so the pool page can show
 * per-address device stats. Display only -- payouts stay by verified proxy shares,
 * so a self-reported number here never affects real-USDT distribution. Best-effort.
 */
export async function reportStats(r: MinerReport): Promise<void> {
  try {
    await netPost(AGENT_REPORT, JSON.stringify(r));
  } catch {
    /* reporting is best-effort; ignore failures */
  }
}

export function findProvider(stats: AgentStats, address: string): ProviderStat | undefined {
  return (stats.providers || []).find((p) => p.address === address);
}
