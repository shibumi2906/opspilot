param([string]$ReportDir='docs/full/evidence/f17/security')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
New-Item -ItemType Directory -Force $ReportDir | Out-Null
$reports=(Resolve-Path -LiteralPath $ReportDir).Path
$archive=Join-Path $PWD '.tools/f17-postgres-image.tar'
$cache='opspilot-full-f14-trivy-cache'
$scanner='aquasec/trivy@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c'
& docker image save -o $archive opspilot-full/postgres:f01
if($LASTEXITCODE){throw 'PostgreSQL image export'}
& docker run --rm --network none --user 0 --entrypoint cp -v "${archive}:/source/image.tar:ro" -v "${cache}:/cache" opspilot-full/app:f01 /source/image.tar /cache/f17-postgres.tar
if($LASTEXITCODE){throw 'PostgreSQL scanner staging'}
& docker run --rm -v "${reports}:/reports" -v "${cache}:/root/.cache/trivy" $scanner image --timeout 20m --db-repository public.ecr.aws/aquasecurity/trivy-db:2 --input /root/.cache/trivy/f17-postgres.tar --scanners vuln --format json --output /reports/postgres-image.json
if($LASTEXITCODE){throw 'PostgreSQL scan failed'}
& docker run --rm -v "${reports}:/reports" -v "${cache}:/root/.cache/trivy" $scanner image --timeout 20m --input /root/.cache/trivy/f17-postgres.tar --format cyclonedx --output /reports/postgres-sbom.json
if($LASTEXITCODE){throw 'PostgreSQL SBOM failed'}
$scan=Get-Content -Raw (Join-Path $reports 'postgres-image.json') | ConvertFrom-Json
$blocking=@($scan.Results | ForEach-Object {$_.Vulnerabilities} | Where-Object {$_ -and $_.Severity -in @('HIGH','CRITICAL')})
if($blocking.Count){throw "PostgreSQL has $($blocking.Count) HIGH/CRITICAL findings; remediation required"}
Write-Output 'PostgreSQL OS/gosu image gate passed; all raw findings and CycloneDX inventory retained.'
