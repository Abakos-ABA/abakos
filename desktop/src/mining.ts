// Composes local miner status (from the Rust core) with the agent's per-provider
// stats (verified shares + earned ABA) for the live displays.
import {
  minerStatus,
  agentStats,
  findProvider,
  type MinerStatus,
  type ProviderStat,
  type AgentStats,
} from "./net";

export { hardwareInfo, startMiner, stopMiner, minerStatus } from "./net";
export type { MinerStatus, ProviderStat, AgentStats } from "./net";

export interface LiveStats {
  miner: MinerStatus;
  agent?: AgentStats;
  provider?: ProviderStat;
}

export async function fetchLive(address: string | null): Promise<LiveStats> {
  const miner = await minerStatus();
  let agent: AgentStats | undefined;
  let provider: ProviderStat | undefined;
  try {
    agent = await agentStats();
    if (address && agent) provider = findProvider(agent, address);
  } catch {
    // agent is optional for the local hashrate display
  }
  return { miner, agent, provider };
}
