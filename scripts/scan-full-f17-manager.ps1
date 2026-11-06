param([string]$ReportDir='docs/full/evidence/f17/security', [string]$Image='opspilot-full/manager:f17')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
New-Item -ItemType Directory -Force $ReportDir | Out-Null
$reports=(Resolve-Path -LiteralPath $ReportDir).Path
$image=$Image
$scanner='aquasec/trivy@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c'
$cache='opspilot-full-f14-trivy-cache'
$archive=Join-Path $PWD '.tools/f17-manager-image.tar'
& docker image save -o $archive $image
if($LASTEXITCODE){throw 'Manager inventory export failed'}
& docker run --rm --network none --user 0 --entrypoint cp -v "${archive}:/source/image.tar:ro" -v "${cache}:/cache" opspilot-full/app:f01 /source/image.tar /cache/f17-manager.tar
if($LASTEXITCODE){throw 'Manager scanner staging failed'}
& docker run --rm -v "${reports}:/reports" -v "${cache}:/root/.cache/trivy" $scanner image --timeout 20m --db-repository public.ecr.aws/aquasecurity/trivy-db:2 --input /root/.cache/trivy/f17-manager.tar --scanners vuln --format json --output /reports/manager-image.json
if($LASTEXITCODE){throw 'Manager image scan failed'}
& docker run --rm -v "${reports}:/reports" -v "${cache}:/root/.cache/trivy" $scanner image --timeout 20m --input /root/.cache/trivy/f17-manager.tar --format cyclonedx --output /reports/manager-sbom.json
if($LASTEXITCODE){throw 'Manager SBOM failed'}
$scan=Get-Content -Raw (Join-Path $reports 'manager-image.json') | ConvertFrom-Json
$blocking=@($scan.Results | ForEach-Object {$_.Vulnerabilities} | Where-Object {$_ -and $_.Severity -in @('HIGH','CRITICAL')})
if($blocking.Count){throw "Manager has $($blocking.Count) HIGH/CRITICAL findings; remediation required"}
Write-Output 'Manager image security gate passed; raw findings and CycloneDX inventory retained.'
