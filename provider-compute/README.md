# Abakos Compute Provider

Turn a Linux machine (local GPU PC, VMware VM, or bare metal) into an **Abakos compute provider**: register on-chain, bid on deployments, run tenant workloads on Kubernetes, and get paid in **native ABA (`uaba`)** via on-chain escrow.

This is the off-chain half of the marketplace. The on-chain modules (deployment / market / provider / escrow / cert) live in [`../chain`](../chain). We run Akash's [`provider-services`](https://github.com/akash-network/provider) daemon patched for Abakos bech32 (`abakos`) and denom (`uaba`).

> **Start here:** [ABA-ONLY.md](ABA-ONLY.md) (single coin) · [MAINNET-PARITY.md](MAINNET-PARITY.md) (sandbox = mainnet architecture)

## Chain parameters

Configured via [`config/network.sh`](config/network.sh) (`ABA_NETWORK=sandbox|mainnet`).

| Field         | Sandbox (`default`)      | Mainnet (`abakos-1`)   |
| ------------- | ------------------------ | ---------------------- |
| chain-id      | `abakos-sandbox-1`       | `abakos-1`             |
| RPC           | `https://rpc.abakos.ai`  | same host at launch    |
| denom         | `uaba`                   | `uaba`                 |
| escrow        | `uaba` only              | `uaba` only            |
| gas           | `0uaba`                  | `0uaba`                |

Marketplace API versions (live on `rest.abakos.ai`): provider `v1beta4`, market `v1beta5`, deployment `v1beta4`. Build `provider-services` from upstream **v0.14.2** with the Abakos sdkutil patch (see `scripts/10-build-provider.sh`).

## Architecture (ABA-only)

```
tenant (abakosd) --MsgCreateDeployment (uaba escrow)--> abakos chain
                              |  open order
                              v
provider-services --bid (uaba)--> chain --lease--> provider-services
                              |
tenant --manifest (HTTPS :8443)--> provider-services --> k3s (container)
                              |
              escrow streams uaba/block --> provider wallet
```

## Prerequisites

- Ubuntu 22.04/24.04 (VMware/Hyper-V VM for CPU-first; GPU needs Hyper-V DDA or bare metal).
- ≥ 4 vCPU, ≥ 8 GB RAM, ≥ 40 GB disk for k3s + test workload.
- Outbound HTTPS to `rpc.abakos.ai`; inbound **8443** for provider gateway (tenants send manifests).
- Go 1.22+, `git`, `jq`, `curl`, `helm`, `kubectl`.
- **`abakosd` from this monorepo** (ABA-only build) on `PATH`.

Copy the sandbox binary from the validator if needed:

```bash
scp root@217.154.169.211:/usr/local/bin/abakosd /usr/local/bin/
sudo chmod +x /usr/local/bin/abakosd
```

## Quick install

**Headless (server):**

```bash
sudo DOMAIN=provider.yourhost.tld bash provider-compute/install.sh
bash provider-compute/scripts/30-test-deploy.sh
```

**Step-by-step:**

| Step | Script | What it does |
| ---- | ------ | ------------ |
| 1 | `scripts/00-install-k3s.sh` | k3s, ingress-nginx, cert-manager, Gateway API CRDs, hostname + inventory operators |
| 2 | `scripts/10-build-provider.sh` | Clone/build `provider-services` (Abakos prefixes) |
| 3 | `scripts/20-register-provider.sh` | Provider key, wallet funding (send ABA yourself — no faucet), cert, `provider create` |
| 4 | systemd / manual `run` | `abakos-provider` service (`systemd/provider-services.service`) |
| 5 | `scripts/30-test-deploy.sh` | Tenant: deploy `examples/hello-cpu.yaml` → bid → lease → manifest |

See [QUICKSTART.md](QUICKSTART.md) for desktop AppImage path and VMware notes.

## Example deployment (SDL)

[`examples/hello-cpu.yaml`](examples/hello-cpu.yaml) — nginx on 0.5 CPU, pricing in **uaba**, SDL **v2.1** with hostname for the hostname operator:

```bash
abakosd tx deployment create examples/hello-cpu.yaml \
  --deposit 5000000uaba --from tenant \
  --chain-id abakos-sandbox-1 --node https://rpc.abakos.ai:443 \
  --keyring-backend test --gas auto --gas-adjustment 1.4 --gas-prices 0uaba -y
```

## Provider daemon flags (important)

- `--bid-deposit 5000000uaba` — bid escrow in native ABA
- `--bid-price-script-path pricing.sh` — outputs **uaba per block**
- `--deployment-ingress-domain` — base domain for lease URIs
- Gateway for tenants: **`https://<host>:8443`** (not 8444)

## Sandbox validator ops

Run on the validator as root:

| Script | When |
| ------ | ---- |
| `scripts/fix-sandbox-aba-only.sh` | After deploying ABA-only `abakosd` — gov params to `uaba` only |
| `scripts/fix-sandbox-oracle.sh` | Only if you need ACT/BME (not required for ABA-only tenants) |

## GPU (later)

CPU-first validates the full flow without a GPU. For renting a 2nd card: Hyper-V DDA (not VMware), NVIDIA GPU Operator, GPU attributes in `provider.yaml`.

## Status (Phase 1)

| Item | Status |
| ---- | ------ |
| k3s + operators | ✅ |
| Provider register + daemon | ✅ |
| Tenant deploy escrow **uaba** | ✅ verified sandbox |
| Provider bid **uaba** | ✅ verified sandbox |
| Lease create | ✅ verified sandbox (dseq `362096`) |
| Manifest + nginx pod | ✅ verified sandbox — SDL v2.1 + `hello.provider.abakos.ai` + hostname operator |

## Docs

- **[MAINNET-PARITY.md](MAINNET-PARITY.md)** — sandbox vs mainnet, DNS, checklist
- **[ABA-ONLY.md](ABA-ONLY.md)** — single-coin model, troubleshooting, ports, SDL
- **[QUICKSTART.md](QUICKSTART.md)** — install.sh vs desktop AppImage path
