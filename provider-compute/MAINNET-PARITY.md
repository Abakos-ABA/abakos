# Mainnet parity

Abakos **sandbox** (`abakos-sandbox-1`) is designed to run the **same software paths** as **mainnet** (`abakos-1`). Differences are genesis, keys, faucet, and economic value — not architecture.

## Same on sandbox and mainnet

| Layer | Mainnet-parity choice |
| ----- | --------------------- |
| Settlement | **Single coin `uaba`** — no ACT/BME for tenants |
| Marketplace | deployment / market / provider / escrow / cert (Akash modules) |
| SDL | **v2.1** with explicit `accept` hostnames (hostname operator) |
| Provider stack | k3s + ingress-nginx + Gateway API + hostname + inventory operators |
| Provider daemon | `provider-services` v0.14.2 + Abakos sdkutil patch |
| Gateway | HTTPS **:8443** (manifest/lease-status); gRPC **:8444** |
| Pricing | `pricing.sh` → **uaba/block** (env-tunable weights) |
| Gas | **0 uaba** (zero-fee L1) |
| EVM | chain id **9721** (same on both networks at launch) |

## Network profiles

All provider-compute scripts source [`config/network.sh`](config/network.sh):

```bash
# Live testnet (default)
export ABA_NETWORK=sandbox

# After abakos-1 genesis (same scripts, different chain id + keyring)
export ABA_NETWORK=mainnet
export ABA_KEYRING_BACKEND=file
```

| Variable | Sandbox | Mainnet (`abakos-1`) |
| -------- | ------- | -------------------- |
| `ABA_CHAIN_ID` | `abakos-sandbox-1` | `abakos-1` |
| `ABA_KEYRING_BACKEND` | `test` | `file` |
| `ABA_FAUCET` | explorer faucet | *(none — fund wallets manually)* |
| `ABA_PROVIDER_DOMAIN` | `provider.abakos.ai` | `provider.abakos.ai` (or your host) |

Keplr / wallet metadata: [`chain/networks/sandbox/chain.json`](../chain/networks/sandbox/chain.json) and [`chain/networks/mainnet/chain.json`](../chain/networks/mainnet/chain.json).

## Provider onboarding (mainnet-shaped)

```bash
export DOMAIN=provider.abakos.ai          # ingress base domain
export PUBLIC_IP=203.0.113.10             # or HOST_URI=https://203.0.113.10:8443
sudo bash provider-compute/install.sh
bash provider-compute/scripts/30-test-deploy.sh
```

On-chain `host` must match the **public** gateway URL (`https://IP:8443` or `https://provider.abakos.ai:8443`).

## Governance (on-chain params)

Run on validator after deploying ABA-only `abakosd`:

```bash
bash provider-compute/scripts/fix-sandbox-aba-only.sh
```

Sets `min_deposits` and `bid_min_deposits` to **uaba only** — same proposal for mainnet launch.

## Intentional sandbox-only differences

| Item | Sandbox | Mainnet at launch |
| ---- | ------- | ----------------- |
| Chain id | `abakos-sandbox-1` | `abakos-1` (new genesis) |
| ABA value | No market value | Real liquidity |
| Faucet | Yes | No |
| Validators | Single hosted node | Multi-validator set |
| uakt/uact alias in binary | Until gov params migrate | Removed after genesis uses uaba only |
| Security audit | In progress | Required gate |

## Pre-mainnet checklist

- [ ] External audit (EVM + marketplace + provider)
- [ ] Gov params: uaba-only on `abakos-1` genesis or day-0 proposal
- [ ] Multi-validator genesis + key ceremony
- [ ] Public CPU/GPU providers with real DNS (`*.provider.abakos.ai`)
- [ ] Console (`console.abakos.ai`) wired to same RPC/SDL
- [ ] Supply-reducing burn module (sandbox uses send-to-dead-address)
- [ ] Remove legacy uakt/uact param alias once all nodes upgraded

## DNS pattern (production)

```
provider.abakos.ai          → provider gateway (8443)
hello.provider.abakos.ai    → lease ingress (from SDL accept + hostname operator)
*.provider.abakos.ai        → wildcard to provider ingress LB (recommended)
```

For local VMs without public DNS, set `DOMAIN=provider.abakos.ai` and add `/etc/hosts` entries for lease hostnames, or use a dev subdomain you control.

Sandbox can use `https://<public-ip>:8443` via an SSH reverse tunnel to the validator until the IONOS A record `provider.abakos.ai` points at that IP. Install with `scripts/tunnel-remote.sh` (TLS passthrough; no Caddy in front of :8443), then set on-chain host with `HOST_URI=https://<public-ip>:8443 bash scripts/40-update-host-uri.sh`. When DNS exists, re-run the update script with `HOST_URI=https://provider.abakos.ai:8443`.

Manual IONOS step (no API): add A record `provider.abakos.ai` → `217.154.169.211` (and open inbound TCP 8443 on that host's cloud firewall).
