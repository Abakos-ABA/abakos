# Add VMware HGFS shared folder for abakos repo (run once, VM should be powered off).
# Usage: powershell -ExecutionPolicy Bypass -File provider-compute/scripts/configure-vmware-shared.ps1
$ErrorActionPreference = 'Stop'
$vmx = "C:\Users\Marlon\Documents\Virtual Machines\Ubuntu 64-bit\Ubuntu 64-bit.vmx"
$shareHost = "C:\Users\Marlon\abakos"
$shareName = "abakos"

if (-not (Test-Path $vmx)) { throw "VMX not found: $vmx" }
if (-not (Test-Path $shareHost)) { throw "Repo not found: $shareHost" }

$lines = Get-Content $vmx
if ($lines -match 'sharedFolder0\.present') {
  Write-Output "Shared folder already configured in VMX."
} else {
  $append = @(
    '',
    'sharedFolder0.present = "TRUE"',
    "sharedFolder0.enabled = `"TRUE`"",
    "sharedFolder0.readOnly = `"FALSE`"",
    "sharedFolder0.hostPath = `"$shareHost`"",
    "sharedFolder0.guestName = `"$shareName`"",
    'sharedFolder0.expiration = "never"',
    'sharedFolder.maxNum = "1"'
  )
  Add-Content -Path $vmx -Value ($append -join "`n")
  Write-Output "Added HGFS shared folder '$shareName' -> $shareHost"
}

Write-Output @"

Next in the Ubuntu VM terminal (user: marlon):
  sudo apt-get install -y open-vm-tools open-vm-tools-desktop
  sudo mount -t fuse.vmhgfs-fuse .host:/abakos /mnt -o allow_other 2>/dev/null || true
  bash /mnt/abakos/provider-compute/scripts/vm-bootstrap.sh

Or enable SSH then from Windows:
  ssh marlon@192.168.227.128
"@
