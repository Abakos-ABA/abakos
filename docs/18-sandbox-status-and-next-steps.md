# Sandbox status and next steps

> Last updated: 2026-07-23  
> Audience: anyone continuing Abakos sandbox work from GitHub.  
> Related repos: [`Abakos-ABA/abakos`](https://github.com/Abakos-ABA/abakos) (monorepo), [`Abakos-ABA/abakos-console`](https://github.com/Abakos-ABA/abakos-console).

This document is the handoff checklist: what is already live, what landed in git, what is broken, and the concrete order of work to finish Console deploys with MetaMask / Keplr.

---

## 1. Live endpoints and hosts

| Role | Value |
|------|--------|
| Chain id (Cosmos) | `abakos-sandbox-1` |
| Base denom | `uaba` (display ABA, 6 decimals) |
| bech32 prefix | `abakos` |
| Key type | `ethsecp256k1` / coinType **60** (same bytes as `0x…` ↔ `abakos1…`) |
| Cosmos RPC | `https://rpc.abakos.ai` |
| Cosmos REST | `https://rest.abakos.ai` |
| EVM chain id | **9721** (`0x25f9`) |
| EVM JSON-RPC | `https://evm-rpc.abakos.ai` |
| Explorer | `https://explorer.abakos.ai` |
| Website | `https://abakos.ai` |
| Console | `https://console.abakos.ai` |
| Provider discovery (on-chain `host_uri`) | often `https://provider.abakos.ai:8443` or `https://<validator-ip>:8443` via tunnel |
| Validator / chain node | `root@217.154.169.211` |
| Web / console / mailcow VPS | `root@217.160.46.61` (do **not** break mailcow; Caddy sites under `/opt/sites/`) |

Gas on sandbox is effectively free for Cosmos txs used in ops scripts (`0uaba` / auto gas). Product docs also describe the zero-fee L1 model; see [`fee-model.md`](fee-model.md).

---

## 2. What is already done

### 2.1 Chain / sandbox

- Public sandbox chain is running (`abakos-sandbox-1`).
- EVM module live on chain id 9721; MetaMask can add the network via `https://evm-rpc.abakos.ai`.
- **EIP-712 encoding wired in the node** so MetaMask `eth_signTypedData_v4` Cosmos txs verify on-chain.
  - Code: [`chain/cmd/akash/cmd/root.go`](../chain/cmd/akash/cmd/root.go)
  - Pattern: `eip712.RegisterInterfaces` + `eip712.SetEncodingConfig` + `legacytx.RegressionTestingAminoCodec = encodingConfig.Amino`
  - Do **not** call full `evmenccodec.RegisterLegacyAminoCodec` on top of the SDK module basics register; that double-registers and panics.
  - Live `abakosd` on the validator was rebuilt/redeployed with this wiring. Spike MsgSend with EIP-712 succeeded against sandbox.

### 2.2 Compute provider path

- Provider-compute install path documented in [`provider-compute/QUICKSTART.md`](../provider-compute/QUICKSTART.md) and [`provider-compute/ABA-ONLY.md`](../provider-compute/ABA-ONLY.md) (tenants settle in `uaba` only).
- Sandbox reachability without public DNS yet:
  - SSH reverse tunnel: [`provider-compute/scripts/tunnel-remote.sh`](../provider-compute/scripts/tunnel-remote.sh) (TLS passthrough to `:8443`; no Caddy in front of the provider port).
  - On-chain `host_uri` update: [`provider-compute/scripts/40-update-host-uri.sh`](../provider-compute/scripts/40-update-host-uri.sh)
  - Notes in [`provider-compute/MAINNET-PARITY.md`](../provider-compute/MAINNET-PARITY.md): open cloud firewall TCP **8443** on the public host; optional IONOS A record `provider.abakos.ai` → `217.154.169.211`.
- Hostname operator required for bids (documented in ABA-ONLY).

### 2.3 Desktop app

- Release **v0.1.12** on GitHub (signed CI).
- GPU mining background stability on Windows (opt miners out of EcoQoS + keep-awake).
- **Host** tab: can drive Linux `abakos-provider` via systemd; on native Windows the UI explains that compute hosting needs Linux/WSL2.
- Mining works on native Windows. Compute hosting (k3s / provider-services) does not; use Ubuntu VM or WSL2 + tunnel.

### 2.4 Console (repo `abakos-console`)

Live site: `https://console.abakos.ai` (Next app + Caddy on `217.160.46.61`).

Landed / deployed pieces:

| Piece | Status | Where |
|-------|--------|--------|
| Sandbox chain config (`slip44: 60`, eth features, `uaba`) | Done | `apps/deploy-web/src/chains/akash-sandbox.ts` |
| Net config RPC/REST → `rpc.abakos.ai` / `rest.abakos.ai` | Done | `packages/net` (`sandbox-2` slot) |
| Provider-proxy upstream (local `127.0.0.1:3040`, not Akash Cloud) | Done | `apps/deploy-web/src/pages/api/provider-proxy/[network].ts` + Caddy |
| MetaMask **EVM** cosmos-kit wallet (bech32 map, EIP-712 amino signer) | Code done; UX blocked (see §3) | `apps/deploy-web/src/wallet/metamask-evm/` |
| Wallet list labels (EVM vs Snap) | Done | `WalletListView.tsx` |
| Preferred sign type `amino` for ethsecp / EIP-712 | Done | `CustomChainProvider.tsx` |
| Keplr suggest with coinType 60 | Config done | same chain file |

Spike results (important for the next engineer):

1. Direct / amino + keccak + ethsecp256k1 pubkey works once the node has EIP-712 encoding config.
2. Connect must **not** spam `personal_sign` for pubkey; pubkey is recovered lazily on first sign and cached under `localStorage` key prefix `abakos:mm-pubkey:`.
3. cosmjs 0.36 pubkey recovery needs `ExtendedSecp256k1Signature.fromFixedLength` then `recoverPubkey(sig, hash)` (argument order mattered).

---

## 3. Critical open bug (blocks Console deploy UX)

### Symptom

After a successful wallet connect (MetaMask **or** Keplr mock):

- cosmos-kit writes account data and `current-wallet` into storage / Fiber state.
- Modal closes.
- MetaMask may show the site as connected.
- React `useChain("akash-sandbox")` still reports **`walletStatus: Disconnected`** / **`isWalletConnected: false`**.
- UI stays on **Connect Wallet**; user cannot create certs or deploy.

This is **not** an EVM RPC misconfig (`eth_chainId` returns `0x25f9`). It is also **not** MetaMask-EVM-only: the same disconnect UI happened with a Keplr mock after accounts were persisted.

### Likely area

- cosmos-kit session sync vs Console wrappers (`CustomChainProvider`, `WalletProvider`, `useSelectedChain`, `cosmosKitStorage` / `pruneStalePersistedWallet`).
- Possible mismatch between persisted wallet name and the wallets array entry (`metamask-evm` vs Snap `metamask`).
- Possible chain name / network store desync (`akash-sandbox` vs networkStore sandbox slot).

### Debug playbook (do this next)

1. Hard-refresh `https://console.abakos.ai` (or local `deploy-web`).
2. Open React DevTools / Fiber or temporary logging around `useChain("akash-sandbox")` and print `walletStatus`, `address`, `username`, `currentWallet`.
3. Inspect `localStorage` for cosmos-kit keys and `abakos:mm-pubkey:*` after connect.
4. Confirm `CustomChainProvider` wallets array order: Keplr, Cosmostation, **metamask-evm**, metamask Snap.
5. Reproduce with Keplr only (no MetaMask) to keep the bug scoped to session UI, not EIP-712.
6. Fix until `isWalletConnected === true` and the header shows the `abakos1…` address.
7. Only then: MetaMask connect → create client cert → deploy SDL against sandbox provider.

### Acceptance criteria for “wallet connect fixed”

- [ ] Connect Keplr (coinType 60 account) → address visible in header within one click, no reconnect loop.
- [ ] Connect MetaMask (EVM) → same; MetaMask may prompt once for network add / account.
- [ ] Refresh page keeps session (or shows a clear reconnect that restores Connected).
- [ ] First signed tx (cert or MsgSend) works: Keplr amino/keccak path and MetaMask EIP-712 path.
- [ ] Deploy create + lease + send-manifest succeeds via Console against a live provider `host_uri`.

---

## 4. What is still missing (ordered)

### P0: unblock Console

1. Fix cosmos-kit Connected propagation (§3).
2. End-to-end smoke from Console: connect → fund (`uaba` spendable) → cert → deployment → bid → lease → manifest.
3. Redeploy console from git after the fix (today some patches may exist only on the VPS; treat GitHub as source of truth going forward).

### P1: provider / hosting UX

1. Confirm tunnel systemd unit stays up across reboot on the provider VM (`tunnel-remote.sh`).
2. IONOS: A record `provider.abakos.ai` → `217.154.169.211`, firewall TCP 8443 open; then `HOST_URI=https://provider.abakos.ai:8443 bash scripts/40-update-host-uri.sh`.
3. Document / implement **WSL2** path for Windows users who want Host tab compute (k3s inside WSL2 + tunnel). Native Windows mining stays as-is.
4. Optional: second provider VM (not on the validator) for production-like separation.

### P1: MetaMask polish (after connect works)

1. Clear UX if MetaMask Snap is selected by mistake (already labeled “Not for Abakos”).
2. Ensure typed-data domain / types stay aligned with on-chain `eip712.SetEncodingConfig` if cosmos/evm upgrades.
3. Regression test script (Node) for EIP-712 MsgSend against sandbox (keep out of prod bundles; do not commit throwaway `tmp-eip712/` junk).

### P2: product / site consistency

1. Marketing site lives in a **separate private repo** (removed from this monorepo). Keep Console CTAs and coinType messaging consistent with coinType **60** (avoid suggesting Cosmos 118 anywhere Abakos keys are involved).
2. Chat / API product surfaces (`chat.abakos.ai`, `api.abakos.ai`) are product goals; treat as separate from Console wallet P0.
3. Public testnet / mainnet genesis and validator set: not this sandbox handoff.

### P2: ops hygiene

1. Prefer SSH keys; rotate any passwords that were ever pasted in chat.
2. Do not put secrets in git (`*.local.yaml` with keys, faucet mnemonics, private keys).
3. After chain binary changes: rebuild `abakosd`, install on validator, restart carefully, smoke `status` + a small bank send.

---

## 5. Repo map (where to work)

| Concern | Repo / path |
|---------|-------------|
| Chain binary + EIP-712 | `abakos` → `chain/` (esp. `cmd/akash/cmd/root.go`) |
| Provider install / tunnel | `abakos` → `provider-compute/` |
| Desktop miner + Host tab | `abakos` → `desktop/` |
| Console UI + wallets | `abakos-console` → `apps/deploy-web/` |
| MetaMask EVM adapter | `abakos-console` → `apps/deploy-web/src/wallet/metamask-evm/` |
| Chain suggest for Keplr | `abakos-console` → `apps/deploy-web/src/chains/akash-sandbox.ts` |
| Provider proxy API route | `abakos-console` → `apps/deploy-web/src/pages/api/provider-proxy/` |

---

## 6. How to deploy / verify (cheat sheet)

### Chain (validator)

```bash
# on build machine, from repo chain/
# build abakosd, scp to 217.154.169.211:/usr/local/bin/abakosd
# systemctl restart <abakosd unit>
abakosd status --node https://rpc.abakos.ai:443
```

Confirm EIP-712 still works with a small amino/EIP-712 MsgSend from a known ethsecp key before calling Console “done”.

### Console (web VPS)

Typical pattern: build `deploy-web`, sync to the console site dir under `/opt/sites/`, keep Caddy snippets for `console.abakos.ai` and `provider-proxy-*` pointing at local Next + `127.0.0.1:3040`. **Never** restart mailcow casually on this host.

### Provider

```bash
# on provider VM
TUNNEL_HOST=217.154.169.211 TUNNEL_USER=root bash provider-compute/scripts/tunnel-remote.sh
HOST_URI=https://217.154.169.211:8443 bash provider-compute/scripts/40-update-host-uri.sh
bash provider-compute/scripts/30-test-deploy.sh   # CLI tenant E2E
```

CLI E2E can pass while Console still fails on the wallet UI bug. Treat them as separate gates.

### Desktop

- Releases: GitHub Actions / tags `v0.1.x` under `desktop/`.
- Mining: Windows OK on 0.1.12+.
- Hosting: Linux AppImage/deb + provider-compute; Windows needs WSL2/VM.

---

## 7. Decision log (do not re-litigate)

| Decision | Choice | Why |
|----------|--------|-----|
| Own chain vs Akash mainnet | Own fork | ABA as settlement / staking asset |
| Key derivation | coinType 60 / ethsecp256k1 | One key for Desktop `0x` and Cosmos `abakos1` |
| MetaMask path | Custom EVM wallet + EIP-712 amino | Snap does not support coinType 60 for Abakos |
| Preferred cosmos-kit sign type | `amino` | Shared path for Keplr ethsecp + MetaMask EIP-712 |
| Provider TLS | End-to-end to provider-services | No reverse-proxy termination on `:8443` |
| Windows hosting | Not native k3s | Document WSL2/Linux; mining stays native |

---

## 8. Suggested first PR after this handoff

1. **abakos-console:** fix Connected state after wallet connect (§3), with a short repro note in the PR.
2. Smoke cert + deploy on sandbox.
3. Only if needed: small follow-up for MetaMask logo / pubkey cache edge cases.

Chain EIP-712 and provider tunnel scripts should already be on `main` in this monorepo after the 2026-07-23 push. Console MetaMask adapter should be on `abakos-console` `main` the same day. If a file is missing on GitHub, prefer restoring from this doc’s paths rather than re-inventing the spike.

---

## 9. Quick “green / red” board

| Area | Green? | Note |
|------|--------|------|
| Sandbox chain up | Yes | rpc/rest/evm public |
| EIP-712 on node | Yes | deployed + spike OK |
| Provider tunnel scripts | Yes | in repo; ops must keep unit alive |
| CLI tenant deploy | Often yes | `30-test-deploy.sh` |
| Desktop mining 0.1.12 | Yes | Windows background fix |
| Desktop Host on Windows | Partial | needs Linux/WSL2 |
| Console MetaMask code | Yes in git | live UX blocked |
| Console shows Connected | **No** | §3 blocker |
| Console E2E deploy | **No** | blocked by Connected |
| provider.abakos.ai DNS | Maybe | manual IONOS A + firewall |
| Public testnet / mainnet | No | later |

When §3 is green, update this file’s board and bump the “Last updated” date.
