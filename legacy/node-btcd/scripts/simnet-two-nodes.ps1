# T0 two-node simnet (Windows PowerShell)
# Terminal 1: seed + miner:
#   go run ./cmd/abkd --simnet --listen :18555 --mine --verifier gemm --params=false
# Terminal 2: follower:
#   go run ./cmd/abkd --simnet --connect 127.0.0.1:18555 --params=false

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "Building abkd..."
go build -o abkd.exe ./cmd/abkd

Write-Host ""
Write-Host "Start follower in another terminal:"
Write-Host "  cd node; .\abkd.exe --simnet --connect 127.0.0.1:18555 --params=false"
Write-Host ""
Write-Host "Starting seed on :18555 (Ctrl+C to stop)..."
.\abkd.exe --simnet --listen ":18555" --mine --verifier gemm --blocks 8 --params=false
