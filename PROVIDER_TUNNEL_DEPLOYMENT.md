# Provider Tunnel & Host URI Deployment Guide

> Last updated: 2026-07-23  
> Status: **Ready for Testing**

## Overview

The provider tunnel scripts enable a provider VM to publish its local gateway (`:8443`) to a public host until DNS is ready.

**Architecture:**
```
Provider VM (local :8443)
    ↓ (SSH reverse tunnel)
Validator Host (217.154.169.211:8443)
    ↓ (public IP)
Tenant → https://217.154.169.211:8443/status
```

**Timeline:**
1. **Tunnel setup:** SSH reverse tunnel via systemd (Tunnel-Remote.sh)
2. **Host URI update:** On-chain registration with tunnel IP/DNS (40-update-host-uri.sh)
3. **DNS cutover:** IONOS A record → provider.abakos.ai (manual DNS)
4. **Final migration:** Re-run 40-update-host-uri.sh with DNS name

---

## Prerequisites

### On Validator (217.154.169.211, root@217.154.169.211)

1. **SSH server config** (`/etc/ssh/sshd_config`):
   ```bash
   # Add or verify:
   AllowTcpForwarding yes
   GatewayPorts clientspecified
   
   # Test:
   sudo sshd -t
   sudo systemctl reload ssh
   ```

2. **Firewall** (IONOS Panel):
   - Open inbound **TCP 8443** for provider requests
   - Note: ssh (port 22) must already be open for tunnel setup

3. **SSH Key** (optional, for automation):
   ```bash
   ssh-keygen -t ed25519 -f /root/.ssh/abakos_tunnel -N ""
   cat /root/.ssh/abakos_tunnel.pub
   # Add to authorized_keys on provider VM if using key auth
   ```

### On Provider VM

1. **Network connectivity:** Outbound SSH to 217.154.169.211:22 (unblocked)
2. **abakosd:** Already running and operator account created
3. **Keyring:** Provider key available (`abakosd keys list`)
4. **Systemd:** Running and enabled

---

## Deployment Steps

### Step 1: SSH Reverse Tunnel Setup

**On Provider VM:**

```bash
# Download tunnel script
git clone https://github.com/Abakos-ABA/abakos.git
cd abakos

# Run tunnel setup
export TUNNEL_HOST=217.154.169.211
export TUNNEL_USER=root
bash provider-compute/scripts/tunnel-remote.sh
```

**Script Actions:**
1. Creates SSH key pair at `~/.ssh/abakos_tunnel` (ed25519)
2. Tests SSH connectivity to `${TUNNEL_USER}@${TUNNEL_HOST}`
3. Creates systemd unit `/etc/systemd/system/abakos-provider-tunnel.service`
4. Enables and starts the service
5. Waits 2 seconds for tunnel to establish

**Output:**
```
== tunnel target: root@217.154.169.211  remote 0.0.0.0:8443 -> 127.0.0.1:8443 ==
== [1/4] tunnel key ==
public key (install on root@217.154.169.211 authorized_keys with comment abakos-provider-tunnel):
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5... abakos-provider-tunnel

== [2/4] test SSH ==
hostname-of-validator

== [3/4] systemd unit /etc/systemd/system/abakos-provider-tunnel.service ==
== [4/4] start ==
```

**Verification:**

```bash
# Check tunnel is active
systemctl status abakos-provider-tunnel
sudo journalctl -u abakos-provider-tunnel -n 20

# Test tunnel connectivity from validator (ssh into validator):
ssh root@217.154.169.211
curl -sk https://127.0.0.1:8443/status
# Should return provider status JSON
```

### Step 2: On-Chain Host URI Update

**On Provider VM:**

```bash
# Set temporary host URI (tunnel IP:port)
export HOST_URI=https://217.154.169.211:8443
bash provider-compute/scripts/40-update-host-uri.sh
```

**Script Actions:**
1. Reads provider address from keyring
2. Updates or creates `provider-register.local.yaml` with HOST_URI
3. Updates `provider.local.yaml` (local daemon config) if present
4. Submits on-chain `abakosd tx provider update` transaction
5. Verifies with query and displays new host_uri

**Output:**
```
== network: sandbox chain=abakos-sandbox-1 ==
== HOST_URI: https://217.154.169.211:8443 ==
provider: abakos1xxxxxxxxxxx

== updating host in provider-register.local.yaml ==
...

== tx provider update ==
gas estimate: 12345
code: 0  # ← success

== verify ==
{
  "owner": "abakos1xxxxxxxxxxx",
  "host_uri": "https://217.154.169.211:8443",
  "attributes": [...]
}

Updated on-chain host_uri to:
  https://217.154.169.211:8443

When DNS is ready, re-run with:
  HOST_URI=https://provider.abakos.ai:8443 bash scripts/40-update-host-uri.sh

IONOS A record (manual): provider.abakos.ai -> 217.154.169.211
```

**Verify Tenant Can Access:**

```bash
# From any machine with outbound HTTPS:
curl -sk https://217.154.169.211:8443/status
# Should return provider status (no certificate error, tunnel is transparent TLS)
```

---

## Testing Stability

### Test 1: Tunnel Persists After Reboot

```bash
# On provider VM:
sudo reboot

# After 2 minutes:
systemctl status abakos-provider-tunnel
# Expected: active (running)

# Check tunnel is still live:
ssh root@217.154.169.211  # from another terminal
curl -sk https://127.0.0.1:8443/status
# Should work
```

### Test 2: Connection Reconnects After Network Blip

```bash
# Simulate network disruption:
sudo systemctl stop networking
sleep 10
sudo systemctl start networking

# Monitor tunnel:
sudo journalctl -u abakos-provider-tunnel -f
# Should see reconnect attempts (ServerAliveInterval=30s)
# After ~60s, tunnel should be back up

curl -sk https://217.154.169.211:8443/status
# Should work again
```

### Test 3: Provider Queries Still Work

```bash
# From validator or any RPC-connected machine:
abakosd query provider get abakos1xxxxxxxxxxx --node https://rpc.abakos.ai
# Should show:
# - host_uri: "https://217.154.169.211:8443"
# - attributes: [tenant requirements...]
```

---

## DNS Migration (When Ready)

### Prerequisites

1. **IONOS account** with domain `provider.abakos.ai`
2. **Validator IP:** 217.154.169.211 (public IP where tunnel reverse-proxies)
3. **Tunnel stable** and passing all tests above

### Steps

1. **IONOS DNS Panel:**
   - Create/update A record: `provider.abakos.ai` → `217.154.169.211`
   - TTL: 300 (or default)
   - Wait for propagation (~5–10 min)

   ```bash
   # Verify DNS resolved:
   nslookup provider.abakos.ai
   # Should show: 217.154.169.211
   ```

2. **Update Host URI on Provider VM:**

   ```bash
   export HOST_URI=https://provider.abakos.ai:8443
   bash provider-compute/scripts/40-update-host-uri.sh
   ```

3. **Verify On-Chain:**

   ```bash
   abakosd query provider get abakos1xxxxxxxxxxx --node https://rpc.abakos.ai -o json | jq '.host_uri'
   # Should show: "https://provider.abakos.ai:8443"
   ```

4. **Test Tenant Access:**

   ```bash
   curl -sk https://provider.abakos.ai:8443/status
   # Should work (DNS resolved to tunnel reverse proxy)
   ```

---

## Troubleshooting

### Issue: Tunnel Fails to Connect

**Error:** `ssh: connect to host 217.154.169.211 port 22: Connection refused`

**Fixes:**
1. Verify outbound SSH open: `ssh -v root@217.154.169.211` (if using key auth, may be password blocked)
2. Check validator sshd: `sudo systemctl status ssh` (on validator)
3. Check IONOS firewall: Ensure inbound TCP 22 is open from provider VM IP (or add rule)

### Issue: Tunnel Connects but Status Returns 403/500

**Error:** `curl -sk https://217.154.169.211:8443/status` returns error

**Fixes:**
1. Verify provider-services is running: `systemctl status abakos-provider` (on provider VM)
2. Check provider logs: `sudo journalctl -u abakos-provider -n 50`
3. Verify local port: `curl -k https://127.0.0.1:8443/status` (on provider VM)
4. If local works but tunnel doesn't: SSH tunnel may have dropped; restart: `sudo systemctl restart abakos-provider-tunnel`

### Issue: Host URI Update Fails (tx error)

**Error:** `abakosd tx provider update` returns code 5 or gas error

**Fixes:**
1. Check provider balance: `abakosd query bank balances abakos1xxx --node https://rpc.abakos.ai`
   - Must have `>= 10000 uaba` for gas
2. Check keyring: `abakosd keys list --keyring-backend file`
3. Verify provider is registered: `abakosd query provider get abakos1xxx --node https://rpc.abakos.ai`
   - If 404: register first with `20-register-provider.sh`
4. Retry with higher gas-adjustment: `abakosd tx provider update ... --gas-adjustment 1.5`

### Issue: DNS Not Resolving

**Error:** `nslookup provider.abakos.ai` shows old IP or timeout

**Fixes:**
1. Check IONOS DNS panel: A record exists and points to 217.154.169.211
2. Wait for TTL expiration (up to 300 sec if set)
3. Flush local DNS cache:
   ```bash
   # Linux
   systemctl restart systemd-resolved
   # macOS
   sudo dscacheutil -flushcache
   # Windows
   ipconfig /flushdns
   ```
4. Query public DNS resolver:
   ```bash
   dig provider.abakos.ai @8.8.8.8
   # Should return 217.154.169.211
   ```

---

## Rollback

If tunnel causes issues and you need to switch back:

1. **Disable tunnel:**
   ```bash
   sudo systemctl stop abakos-provider-tunnel
   sudo systemctl disable abakos-provider-tunnel
   ```

2. **Revert host_uri to static IP** (if you have direct access):
   ```bash
   export HOST_URI=https://your-provider-static-ip:8443
   bash provider-compute/scripts/40-update-host-uri.sh
   ```

3. **Or use alternate provider registration** (if provider-services restart fails):
   ```bash
   abakosd tx provider update provider-register.bak.yaml --from provider -y
   ```

---

## References

- **Tunnel script:** [provider-compute/scripts/tunnel-remote.sh](https://github.com/Abakos-ABA/abakos/blob/main/provider-compute/scripts/tunnel-remote.sh)
- **Host URI script:** [provider-compute/scripts/40-update-host-uri.sh](https://github.com/Abakos-ABA/abakos/blob/main/provider-compute/scripts/40-update-host-uri.sh)
- **Provider quickstart:** [provider-compute/QUICKSTART.md](https://github.com/Abakos-ABA/abakos/blob/main/provider-compute/QUICKSTART.md)
- **Network config:** [provider-compute/config/network.sh](https://github.com/Abakos-ABA/abakos/blob/main/provider-compute/config/network.sh)
