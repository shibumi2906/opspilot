param([string]$ReportDir='docs/full/evidence/f09/security')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$scanner='aquasec/trivy@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c'
New-Item -ItemType Directory -Force $ReportDir,'.tools/trivy-cache' | Out-Null
$reports=(Resolve-Path -LiteralPath $ReportDir).Path
$cache=(Resolve-Path -LiteralPath '.tools/trivy-cache').Path
& docker pull $scanner
if($LASTEXITCODE){throw 'Pinned image scanner unavailable; security gate blocked'}
foreach($name in @('app','web')){
    $archive=Join-Path (Get-Location) ".tools/f09-scan-$name.tar"
    & docker image save -o $archive "opspilot-full/${name}:f01"
    if($LASTEXITCODE){throw "Image inventory unavailable: $name"}
    & docker run --rm -v "${archive}:/artifact/image.tar:ro" -v "${reports}:/reports" -v "${cache}:/root/.cache/trivy" $scanner --quiet image --timeout 20m --input /artifact/image.tar --scanners vuln --format json --output "/reports/$name-image.json"
    if($LASTEXITCODE){throw "Image scanner failed for $name; no passing claim"}
    $result=Get-Content -Raw -LiteralPath (Join-Path $reports "$name-image.json") | ConvertFrom-Json
    $blocking=@($result.Results | ForEach-Object { $_.Vulnerabilities } | Where-Object { $_ -and $_.Severity -in @('HIGH','CRITICAL') })
    if($blocking.Count){throw "$name has $($blocking.Count) HIGH/CRITICAL findings; remediation required"}
}
& docker run --rm -u root -v "${reports}:/reports" opspilot-full/tests:f01 uv tool run pip-audit==2.10.1 --path /app/.venv/lib/python3.12/site-packages --format json --output /reports/python-audit.json
if($LASTEXITCODE){throw 'Python dependency audit gate failed'}
& docker run --rm -v "${reports}:/reports" --entrypoint sh opspilot-full/e2e:f01 -c 'npm audit --json > /reports/npm-audit.json'
if($LASTEXITCODE){throw 'npm dependency audit gate failed'}
& docker run --rm opspilot-full/app:f01 python -c "import ssl; assert not any('emSign ECC Root CA - G3' in str(c.get('subject')) for c in ssl.create_default_context().get_ca_certs())"
if($LASTEXITCODE){throw 'Compromised TLS trust anchor remains in runtime'}
Write-Host 'Runtime image HIGH/CRITICAL gate and package audits passed; all scan findings preserved.'
