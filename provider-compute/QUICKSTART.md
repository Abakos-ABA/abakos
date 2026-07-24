# Quickstart — Abakos compute provider

Run on a **dedicated Ubuntu 22.04/24.04 VM** (not on the chain validator VPS).

> **Tenants pay in `uaba` only** — no ACT minting. Read [ABA-ONLY.md](ABA-ONLY.md) first.

## 0) Install `abakosd` (ABA-only build)

From the validator or after building `../chain`:

```bash
scp root@217.154.169.211:/usr/local/bin/abakosd /usr/local/bin/
sudo chmod +x /usr/local/bin/abakosd
```

## A) Headless server (recommended)

```bash
git clone https://github.com/Abakos-ABA/abakos.git
cd abakos
sudo DOMAIN=provider.yourhost.tld bash provider-compute/install.sh
```

Then tenant E2E test (separate key from provider):

```bash
bash provider-compute/scripts/30-test-deploy.sh
```

### Manual steps

```bash
bash provider-compute/scripts/00-install-k3s.sh    # includes Gateway API + hostname operator
bash provider-compute/scripts/10-build-provider.sh
bash provider-compute/scripts/20-register-provider.sh
sudo systemctl enable --now abakos-provider
bash provider-compute/scripts/30-test-deploy.sh
```

## B) Desktop app (Host tab)

```bash
bash desktop/scripts/build-linux.sh
# AppImage / .deb in desktop/src-tauri/target/release/bundle/
```

The **Host** tab starts/stops the local `abakos-provider` systemd unit and shows on-chain `host_uri`.
Install provider-compute on the Linux VM first (Phase 1). Public reachability still needs a tunnel or public IP — see `scripts/tunnel-remote.sh`.

## Tenant flow (30-test-deploy.sh)

1. Create `tenant` key + faucet → **250 ABA** (`uaba`)
2. Publish client certificate
3. `deployment create` with `5000000uaba` deposit
4. Wait for provider bid (`uaba` price + bid deposit)
5. `lease create`
6. `send-manifest` via **`--provider-url https://<provider-ip>:8443`**

## Checklist before E2E

- [ ] `abakosd` is ABA-only build (post 2026-07-22)
- [ ] Provider wallet holds ≥ 6 ABA for bid deposits (self-funded — registration no longer uses the faucet)
- [ ] `kubectl get pods -n akash-services` — `operator-hostname` **Running**
- [ ] `systemctl is-active abakos-provider`
- [ ] Tenant has `uaba` in **spendable-balances** (not just `aba` in `balances`)
- [ ] SDL is **v2.1** with `accept:` hostname — see `examples/hello-cpu.yaml`

## Common issues

| Symptom | Fix |
| ------- | --- |
| No bids | Install hostname operator — [ABA-ONLY.md](ABA-ONLY.md#hostname-operator-required-for-bids) |
| `no uaba balance` | Use `query bank spendable-balances` |
| Faucet cooldown | Wait or reuse funded key |
| Manifest hostname error | SDL v2.1 + `accept:` list |
| send-manifest EOF | Use port **8443**, not 8444 |

## Zero fees

All txs: `--gas-prices 0uaba --gas auto --gas-adjustment 1.4`
