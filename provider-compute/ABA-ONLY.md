# ABA-only compute market (single coin)

Abakos compute runs on **one tenant-facing coin: native `uaba` (ABA)**. Tenants fund deployments from the faucet, escrow `uaba` on-chain, and pay providers in `uaba` per block. There is **no ACT (`uact`), no BME mint, and no oracle price feed** required for the standard deploy → bid → lease → manifest flow.

This document explains the model, what changed in chain/SDK, how to run provider-compute end-to-end, and how to fix common sandbox issues.

---

## Why one coin?

| Old dual-token model | ABA-only (current) |
| -------------------- | ------------------ |
| Tenant gets `uaba` from faucet | Same |
| Must `mint-act` / burn-mint to `uact` for escrow | **Deposit `uaba` directly** |
| SDL pricing in `uact` | SDL pricing in **`uaba`** |
| Oracle `aba/usd` required for BME | **Not required for tenants** |
| Provider bid deposit in `uact` | Provider bid deposit in **`uaba`** |

ACT/BME may remain in the codebase for future use, but **sandbox Phase 1** is validated with ABA only.

---

## Chain & SDK changes (summary)

These live in `../chain` and `../chain-sdk` (same monorepo):

| Area | Change |
| ---- | ------ |
| **Deployment params** | Default min deposit = `uaba`; governance validation requires `uaba` |
| **Deployment handler** | New deployments escrow `uaba`; pricing denom must be `uaba`; `uact` deposits rejected on create |
| **Legacy params** | On-chain params may still list `uakt`/`uact` until gov proposal passes — handler accepts `uaba` via alias to `uakt` min deposit |
| **Market handler** | Provider bid deposits in `uaba` accepted (alias when only `uakt` in `bid_min_deposits`) |
| **SDL schema** | Pricing `denom` enum: **`uaba` only** |
| **CLI** | `abakosd tx deployment create` defaults deposit to `uaba` from chain params |

After pulling this repo, **rebuild and deploy `abakosd`** on validators before tenants can create `uaba` deployments. Sandbox validator was upgraded 2026-07-22.

### Sandbox governance (clean params)

Expedited proposal **#2** (`scripts/fix-sandbox-aba-only.sh`) sets deployment + market params to `uaba` only. Until it passes (~24h expedited voting), the **uaba→uakt alias** in the binary keeps the sandbox working with legacy on-chain params.

Oracle proposal **#1** (for ACT/BME) is **optional** for ABA-only tenants.

---

## Tenant quick start (faucet → deploy)

Prerequisites: `abakosd` built from this monorepo (ABA-only handlers), keyring, client cert.

```bash
# 1) Key + faucet (250 ABA on sandbox)
abakosd keys add tenant --keyring-backend test
TADDR=$(abakosd keys show tenant -a --keyring-backend test)
curl -sS -X POST https://explorer.abakos.ai/faucet \
  -H 'content-type: application/json' \
  -d "{\"address\":\"$TADDR\"}"

# 2) Check spendable balance (use spendable-balances, not balances — see Troubleshooting)
abakosd query bank spendable-balances "$TADDR" \
  --node https://rpc.abakos.ai:443 -o json | jq '.balances'

# 3) Client certificate (required once per key)
TX="--chain-id abakos-sandbox-1 --node https://rpc.abakos.ai:443 \
  --keyring-backend test --gas auto --gas-adjustment 1.4 --gas-prices 0uaba -y"
abakosd tx cert generate client --from tenant $TX
abakosd tx cert publish client --from tenant $TX

# 4) Deploy (escrows uaba) — use examples/hello-cpu.yaml (SDL v2.1 + hostname)
abakosd tx deployment create provider-compute/examples/hello-cpu.yaml \
  --deposit 5000000uaba --from tenant $TX
```

Or run the full scripted flow on a machine with a provider already registered:

```bash
bash provider-compute/scripts/30-test-deploy.sh
```

**Verified on sandbox (2026-07-22):**

- Deployment create with `5000000uaba` escrow — tx `48AB3502…` / `DF6CBD01…`
- Provider bid at `1 uaba/block` with `5000000uaba` bid deposit escrow
- Lease **active** for tenant `abakos159lpq7…`, provider `abakos13ftax…`

---

## Provider setup

### Install order

1. `scripts/00-install-k3s.sh` — k3s, ingress-nginx, cert-manager, **Gateway API CRDs**, hostname + inventory operators
2. `scripts/10-build-provider.sh` — `provider-services` with Abakos bech32/denom patch
3. `scripts/20-register-provider.sh` — on-chain `MsgCreateProvider`
4. systemd / `provider-services run` — bids use `--bid-deposit 5000000uaba`

### Hostname operator (required for bids)

The provider **will not bid** until `operator-hostname` is running. The hostname operator Helm chart needs **Gateway API** `HTTPRoute` CRDs:

```bash
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.0/standard-install.yaml
helm upgrade --install akash-hostname-operator akash/akash-hostname-operator -n akash-services
kubectl get pods -n akash-services   # expect operator-hostname + operator-inventory
```

`00-install-k3s.sh` installs these automatically on fresh clusters.

### Ports: 8443 vs 8444

| Port | Service |
| ---- | ------- |
| **8443** | HTTPS gateway (manifest upload, lease status) — use `--provider-url https://<host>:8443` |
| **8444** | gRPC (provider internal) — **not** for `send-manifest` |

On-chain `host_uri` may still say `:8443`; the daemon listens on both. Tenant CLI:

```bash
provider-services send-manifest examples/hello-cpu.yaml \
  --dseq <DSEQ> --provider <PROVIDER> --from tenant \
  --keyring-backend test --node https://rpc.abakos.ai:443 \
  --provider-url https://<provider-ip>:8443
```

(`provider-services` has **no** `--chain-id` flag — only `--node`.)

### SDL requirements (manifest)

With the hostname operator enabled, **global HTTP exposes must list a hostname** (SDL **v2.1**):

```yaml
version: "2.1"
services:
  web:
    image: nginx:1.27
    expose:
      - port: 80
        as: 80
        accept:
          - hello.provider.abakos.local   # required
        to:
          - global: true
profiles:
  placement:
    abakos:
      pricing:
        web:
          denom: uaba
          amount: 100000
```

Use the **same SDL file** for `deployment create` and `send-manifest`. If you change the SDL after creating the deployment, create a **new deployment** (new `dseq`).

---

## Architecture (ABA escrow)

```
Tenant (uaba) ──MsgCreateDeployment──► Chain escrow (uaba)
                        │
                        ▼
              Provider bids (uaba deposit)
                        │
                        ▼
              Lease active → manifest → k3s pod
                        │
                        ▼
         Escrow streams uaba/block → provider
```

All escrow accounts show `denom: uaba` in `abakosd query deployment list` and bid queries.

---

## Troubleshooting

### `no uaba balance` but faucet succeeded

`query bank balances` may show display denom `aba`. Use **spendable** micro denom:

```bash
abakosd query bank spendable-balances <addr> --node https://rpc.abakos.ai:443 -o json
```

### Faucet `cooldown`

Sandbox faucet rate-limits per address. Wait `retry_after_s` or use an existing funded key.

### `Invalid deposit denomination uaba`

Validator binary is too old — deploy ABA-only `abakosd` and/or wait for gov proposal #2.

### No provider bids

1. `systemctl status abakos-provider` — running?
2. `kubectl get pods -n akash-services` — **operator-hostname** up?
3. Provider has `uaba` for bid deposit? (`spendable-balances` on provider address)
4. `journalctl -u abakos-provider -f` — look for `bid complete` or errors

### `manifest rejected: must have a hostname`

Add `accept: [your.host.name]` under `expose` and use SDL **version: "2.1"**. Redeploy if the on-chain deployment was created with an older SDL.

### `manifest version validation failed`

Manifest SDL must match the deployment hash. Create a new deployment with the final SDL, then send manifest for that `dseq`.

### `send-manifest` EOF on :8444

Use **:8443** with `--provider-url`.

---

## Scripts reference

| Script | Purpose |
| ------ | ------- |
| `install.sh` | One-shot headless install + systemd |
| `scripts/00-install-k3s.sh` | k3s + operators + Gateway API |
| `scripts/10-build-provider.sh` | Build `provider-services` |
| `scripts/20-register-provider.sh` | Register provider on-chain |
| `scripts/30-test-deploy.sh` | Tenant E2E (uaba only) |
| `scripts/fix-sandbox-aba-only.sh` | Gov proposal: uaba-only params (run on validator) |
| `scripts/fix-sandbox-oracle.sh` | Gov proposal: oracle feeders (optional for ABA-only) |

---

## Related docs

- [README.md](README.md) — provider-compute overview
- [QUICKSTART.md](QUICKSTART.md) — install paths (headless vs desktop)
- `../chain` — node binary and modules
- `../chain-sdk` — protos, SDL, CLI
