param([string]$ReportDir='docs/full/evidence/f19/security',[switch]$AuditsOnly,[switch]$SkipApp,[switch]$SkipAudits)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$scanner='aquasec/trivy@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c'
New-Item -ItemType Directory -Force $ReportDir | Out-Null
$reports=(Resolve-Path -LiteralPath $ReportDir).Path
$cache='opspilot-full-f14-trivy-cache'
$images=@{app='opspilot-full/app:f19';prometheus='opspilot-full/prometheus:f19'}
if(-not $AuditsOnly){
$names=if($SkipApp){@('prometheus')}else{@('app','prometheus')}
foreach($name in $names){
    $archive=Join-Path (Get-Location) ".tools/f19-$name-image.tar"
    & docker image save -o $archive $images[$name]
    if($LASTEXITCODE){throw "Image archive failed: $name"}
    & docker run --rm --network none --user 0 --entrypoint cp -v "${archive}:/source/image.tar:ro" -v "${cache}:/cache" opspilot-full/app:f19 /source/image.tar "/cache/f19-$name-image.tar"
    if($LASTEXITCODE){throw 'Scanner archive staging failed'}
    & docker run --rm -v "${reports}:/reports" -v "${cache}:/root/.cache/trivy" $scanner --quiet image --db-repository public.ecr.aws/aquasecurity/trivy-db:2 --timeout 20m --input "/root/.cache/trivy/f19-$name-image.tar" --scanners vuln --format json --output "/reports/$name-image.json"
    if($LASTEXITCODE){throw "Image scan failed: $name"}
    $result=Get-Content -Raw (Join-Path $reports "$name-image.json") | ConvertFrom-Json
    $blocking=@($result.Results | ForEach-Object { $_.Vulnerabilities } | Where-Object { $_ -and $_.Severity -in @('HIGH','CRITICAL') })
    if($blocking.Count){throw "$name raw HIGH/CRITICAL findings: $($blocking.Count); no passing claim"}
}
}
if(-not $SkipAudits){
& docker run --rm -u root -v "${reports}:/reports" opspilot-full/tests:f19 uv tool run pip-audit==2.10.1 --path /app/.venv/lib/python3.12/site-packages --format json --output /reports/python-audit.json
if($LASTEXITCODE){throw 'Python audit gate failed'}
& docker run --rm -v "${reports}:/reports" --entrypoint sh opspilot-full/e2e:f01 -c 'npm audit --json > /reports/npm-audit.json'
if($LASTEXITCODE){throw 'npm audit gate failed'}
}
Write-Output 'Requested F19 supply-chain gates passed; retained reports record full scope'
