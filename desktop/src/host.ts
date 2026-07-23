// Local compute-provider (Host) tab helpers — systemd unit + on-chain host_uri.
import {
  providerDaemonStatus,
  startProvider,
  stopProvider,
  chainProvider,
  type HostProviderStatus,
} from "./net";

export { providerDaemonStatus, startProvider, stopProvider, chainProvider };
export type { HostProviderStatus };

export interface HostLive {
  daemon: HostProviderStatus;
  chainHostUri: string | null;
}

export async function fetchHostLive(owner: string | null): Promise<HostLive> {
  const daemon = await providerDaemonStatus();
  let chainHostUri: string | null = null;
  if (owner) {
    const p = await chainProvider(owner);
    chainHostUri = p?.host_uri ?? null;
  }
  return { daemon, chainHostUri };
}
