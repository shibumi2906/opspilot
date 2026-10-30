param([string]$ReportDir='docs/full/evidence/f14/security')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$scanner='aquasec/trivy@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c'
New-Item -ItemType Directory -Force $ReportDir | Out-Null
$reports=(Resolve-Path -LiteralPath $ReportDir).Path
# Serialize with an optional concurrent cache warmup; never consume a partial Java index.
$warming=(& docker ps -q --filter 'name=^/opspilot-full-f14-java-db-download$')
if($warming){ & docker wait $warming | Out-Null }
& docker run --rm --network none --entrypoint /usr/bin/java opspilot-full/oidc:f03 -Xmx64m -cp /opt/opspilot-probes OpsIdentityProbe *> (Join-Path $reports 'idp-runtime.txt')
if($LASTEXITCODE){throw 'IdP runtime version, Guava or default truststore check failed'}
$archive=Join-Path $PWD '.tools/f14-oidc-final.tar'
& docker image save -o $archive opspilot-full/oidc:f03
if($LASTEXITCODE){throw 'IdP image export failed'}
& docker run --rm --network none --user 0 --entrypoint cp -v "${archive}:/source/image.tar:ro" -v opspilot-full-f14-trivy-cache:/cache opspilot-full/app:f01 /source/image.tar /cache/oidc-final.tar
if($LASTEXITCODE){throw 'IdP archive staging failed'}
& docker run --rm -v "${reports}:/reports" -v opspilot-full-f14-trivy-cache:/root/.cache/trivy $scanner image --timeout 20m --db-repository public.ecr.aws/aquasecurity/trivy-db:2 --java-db-repository public.ecr.aws/aquasecurity/trivy-java-db:1 --input /root/.cache/trivy/oidc-final.tar --scanners vuln --format json --output /reports/oidc-image.json
if($LASTEXITCODE){throw 'IdP image scan failed'}
$result=Get-Content -Raw (Join-Path $reports 'oidc-image.json') | ConvertFrom-Json
$blocking=@($result.Results | ForEach-Object {$_.Vulnerabilities} | Where-Object {$_ -and $_.Severity -in @('HIGH','CRITICAL')})
if($blocking.Count){
    & .venv/Scripts/python.exe scripts/check-f14-idp-applicability.py --archive $archive --scan (Join-Path $reports 'oidc-image.json') --output (Join-Path $reports 'vulnerability-applicability.json')
    if($LASTEXITCODE){throw 'IdP applicable HIGH/CRITICAL gate failed; raw report retained'}
}
