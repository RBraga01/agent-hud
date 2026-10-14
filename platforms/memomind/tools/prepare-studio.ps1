param(
    [string]$SdkRoot = (Join-Path $PSScriptRoot '..\vendor\plugin-open-platform')
)

$ErrorActionPreference = 'Stop'
$platformRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$sdk = (Resolve-Path $SdkRoot).Path
$expectedCommit = 'f74ee53eb70b008e665adfd81ff8a78a344a4ecb'
$actualCommit = (& git -C $sdk rev-parse HEAD).Trim()
if ($actualCommit -ne $expectedCommit) {
    throw "MemoMind SDK commit must be $expectedCommit; found $actualCommit"
}

$buildRoot = Join-Path $platformRoot 'glasses\.build-studio'
$gmpPath = Join-Path $buildRoot 'glasses\glasses.gmp'
Push-Location $platformRoot
try {
    & npm test
    if ($LASTEXITCODE -ne 0) { throw 'Phone tests failed' }
    & python -m pytest tests -q
    if ($LASTEXITCODE -ne 0) { throw 'MemoMind tests failed' }
    & python (Join-Path $sdk 'GlassSDK\build.py') build --project glasses --build-dir $buildRoot
    if ($LASTEXITCODE -ne 0) { throw 'Glasses build failed' }

    New-Item -ItemType Directory -Force phone\vendor, artifacts | Out-Null
    Copy-Item (Join-Path $sdk 'PhoneSDK\examples\life-desk\vendor\gm-plugin-web-sdk.esm.js') phone\vendor\ -Force
    & node (Join-Path $sdk 'PhoneSDK\tools\build-mmpkg.mjs') phone artifacts\agent-hud.mmpkg
    if ($LASTEXITCODE -ne 0) { throw 'Phone package failed' }
    & python (Join-Path $sdk '.agents\skills\memomind-example-app\scripts\check_pair.py') `
        --web artifacts\agent-hud.mmpkg `
        --glass glasses\manifest.json `
        --gmp $gmpPath
    if ($LASTEXITCODE -ne 0) { throw 'Pair metadata check failed' }

    Get-FileHash $gmpPath, artifacts\agent-hud.mmpkg |
        Select-Object Path, Algorithm, Hash
    Write-Host 'Studio pair ready with validated input Mapping B.'
} finally {
    Pop-Location
}
