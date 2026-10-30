param([switch]$CheckMvp)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$root=(Get-Location).Path
$locator=Get-Content -Raw -LiteralPath '.tools/opspilot-full-workspace.json' | ConvertFrom-Json
if($root -ne $locator.path){throw 'Workspace locator does not match this checkout'}
$common=(& git rev-parse --path-format=absolute --git-common-dir).Trim().Replace('/','\')
if($LASTEXITCODE -or $common -ne (Join-Path $root '.git')){throw 'Independent Git storage expected'}
& git merge-base --is-ancestor 4733998 HEAD
if($LASTEXITCODE){throw 'F15 history missing'}
foreach($path in @('.env','.tools/cache/password','.tools/cache/signing-key','.tools/service-keys/private/current.pem')){
    if(-not(Test-Path -LiteralPath $path)){throw "Missing required local state: $path"}
    & git check-ignore --quiet -- $path
    if($LASTEXITCODE){throw "Local state must remain ignored: $path"}
}
& .venv/Scripts/python.exe -c "import pathlib,opspilot; assert pathlib.Path(opspilot.__file__).resolve().is_relative_to(pathlib.Path.cwd()/'src'); print('Python imports this Ops checkout')"
if($LASTEXITCODE){throw 'Ops Python environment failed'}
& node --version
if($LASTEXITCODE){throw 'Node unavailable'}
if(-not(Test-Path -LiteralPath 'web/node_modules/typescript/bin/tsc')){throw 'Web dependencies missing'}
& docker compose --env-file .env -p opspilot-full -f compose.full.yaml config --quiet
if($LASTEXITCODE){throw 'Full compose configuration invalid'}
if($CheckMvp){
    & ./scripts/check-full-isolation.ps1 -MvpPath $locator.mvp_path -ReportPath '.tools/ops-isolation-check.json'
    if($LASTEXITCODE){throw 'MVP preservation gate failed'}
}
Write-Output 'Ops workspace, local state, locked dependencies and compose configuration verified.'
