# Clone btcd and apply Abakos PoUW patches (Windows)
# Creates node/.btcd-fork/ (gitignored) at btcsuite/btcd v0.24.2
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$fork = Join-Path $root ".btcd-fork"
$patch = Join-Path $root "fork\patches\abakos-pouw.patch"
$tag = "v0.24.2"

if (Test-Path $fork) {
  Write-Host "Already exists: $fork"
  Write-Host "Delete it to re-clone, or run: git -C $fork apply $patch"
  exit 0
}

Write-Host "Cloning btcd $tag into $fork ..."
git clone --depth 1 --branch $tag https://github.com/btcsuite/btcd.git $fork

Push-Location $fork
git checkout -b abakos-pouw
if (-not (Test-Path $patch)) {
  throw "Missing patch file: $patch"
}
git apply $patch
if ($LASTEXITCODE -ne 0) {
  Pop-Location
  throw "git apply failed, check fork/patches/abakos-pouw.patch"
}
Pop-Location

Write-Host ""
Write-Host "Done. node/go.mod should contain:"
Write-Host "  replace github.com/btcsuite/btcd => ./.btcd-fork"
Write-Host ""
Write-Host "Verify: cd node && go test ./fork/..."
