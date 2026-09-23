# RandomX huge pages — automatic, provider-wide

RandomX (the CPU algo behind Abakos mining) runs a ~2080 MiB dataset. Backing it
with **huge pages** instead of 4 KiB pages removes TLB misses — typically
**+30–50 % hashrate**, i.e. that much more ABA minted for the same power.

The goal here is **scale**: it must work for *every* future provider and *every*
one of the 391 Console templates (OpenClaw, Razer-AIKit, ComfyUI, DeepSeek, the
Mining templates, …) with **no per-template config, no special SDL, no commands for
the leaser — plain vanilla Linux.**

## How it works: Transparent Huge Pages, set automatically

An Akash/Console SDL exposes only cpu / memory / storage / gpu. A tenant pod
**cannot** request `hugepages-2Mi` resources, add Linux capabilities, or touch
`/dev/cpu/*/msr`. So the only huge-page lever that reaches an ordinary pod is
**Transparent Huge Pages (THP)** — a host kernel feature that transparently promotes
any process's large allocations (like RandomX's 2 GB dataset) to 2 MiB pages, with
zero cooperation from the container.

So every provider node is tuned **once, automatically, at onboarding**:

- `scripts/00-install-k3s.sh` → step [7/7] runs `scripts/62-install-node-tune.sh`,
  which installs and enables **`abakos-node-tune.service`**.
- That service sets `transparent_hugepage/enabled = always` and
  `defrag = defer+madvise`, and loads the `msr` module — **at every boot**.
- It reserves **no** fixed huge pages on purpose: a static reservation would remove
  RAM from what the provider can rent out. THP promotes on demand, so rentable lease
  memory is untouched.

Result: any deployment scheduled on the node — any template, any leaser — that mines
RandomX gets huge pages automatically. Nobody types a command.

```bash
# Already automatic via 00-install-k3s.sh. To (re-)apply on an existing node:
sudo bash scripts/62-install-node-tune.sh

# verify
cat /sys/kernel/mm/transparent_hugepage/enabled     # -> always [madvise] never
systemctl status abakos-node-tune.service
```

### The one honest ceiling: MSR

The **MSR mod** (another ~5–15 %) writes model-specific CPU registers and needs
`SYS_RAWIO` / root — which an unprivileged tenant pod can never have. That part is
simply not deliverable to arbitrary Console templates on vanilla Linux, and no
config changes that. THP is the portion that *is* universal, and it's the bulk of
the win. MSR is only reachable by a host-level miner (below).

## Optional: mine idle CPU on the provider host itself

Separate from tenant deployments, a provider can mint its **idle** CPU with a host
miner that yields to paid leases. This path is privileged (root), so it gets the
**full** win — explicit 2 MiB/1 GiB pages **and** the MSR mod:

```bash
sudo -E bash scripts/60-hugepages.sh      # reserve explicit pages (+ ABA_HUGEPAGES_1G for 1 GiB, needs reboot)
sudo -E bash scripts/61-install-miner.sh  # xmrig as a service: fast mode, huge pages, MSR, autostart
```

Optional and off unless the operator runs it. See the script headers for knobs
(`ABA_MINER_ADDR`, `ABA_MINER_MAX_CPU`, `ABA_HUGEPAGES_1G`, …). The miner logs in as
`ADDR.WORKER`, already labelled for the coming worker-labels feature.

## Desktop app

Just works — no commands. xmrig attempts 2 MiB huge pages by default and falls back
silently (only lower hashrate) if the OS won't grant them. The bigger levers are
**off by default** because on Windows they need admin + the WinRing0 kernel driver,
a frequent antivirus false-positive on a consumer app. Advanced users can opt in per
launch with `ABA_MINER_1GB=1` / `ABA_MINER_MSR=1`, but nothing requires it.

## Verify a pod is actually getting huge pages

```bash
grep -i AnonHugePages /proc/meminfo          # climbs once a RandomX pod is running
cat /sys/kernel/mm/transparent_hugepage/enabled
# host miner only:
journalctl -u abakos-miner | grep -iE 'huge pages|msr'
```
