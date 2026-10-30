param([string]$ReportDir='docs/full/evidence/f15/security')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$cache='opspilot-full-f14-trivy-cache'
& ./scripts/scan-full-security.ps1 -ReportDir $ReportDir -CacheVolume $cache
if($LASTEXITCODE){throw 'App/web/package security gate'}
& ./scripts/scan-full-f14-identity.ps1 -ReportDir $ReportDir
if($LASTEXITCODE){throw 'IdP security gate'}
$reports=(Resolve-Path -LiteralPath $ReportDir).Path
$archive=Join-Path $PWD '.tools/f15-redis-final.tar'
& docker image save -o $archive opspilot-full/redis:f15
if($LASTEXITCODE){throw 'Redis image export'}
& docker run --rm --network none --user 0 --entrypoint cp -v "${archive}:/source/image.tar:ro" -v "${cache}:/cache" opspilot-full/app:f01 /source/image.tar /cache/redis-final.tar
if($LASTEXITCODE){throw 'Redis archive staging'}
$scanner='aquasec/trivy@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c'
& docker run --rm -v "${reports}:/reports" -v "${cache}:/root/.cache/trivy" $scanner image --timeout 20m --db-repository public.ecr.aws/aquasecurity/trivy-db:2 --input /root/.cache/trivy/redis-final.tar --scanners vuln --format json --output /reports/redis-image.json
if($LASTEXITCODE){throw 'Redis image scan'}
$scan=Get-Content -Raw (Join-Path $reports 'redis-image.json') | ConvertFrom-Json
$blocking=@($scan.Results | ForEach-Object {$_.Vulnerabilities} | Where-Object {$_ -and $_.Severity -in @('HIGH','CRITICAL')})
if($blocking.Count){throw "Redis image has $($blocking.Count) HIGH/CRITICAL findings"}
Write-Output 'F15 app/web/Redis runtime image and package gates passed; raw IdP applicability retained separately.'
