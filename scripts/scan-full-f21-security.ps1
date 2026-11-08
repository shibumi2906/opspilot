param([string]$ReportDir='docs/full/evidence/f21/security')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$scanner='aquasec/trivy@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c'
$cache='opspilot-full-f14-trivy-cache'
New-Item -ItemType Directory -Force $ReportDir | Out-Null
$reports=(Resolve-Path -LiteralPath $ReportDir).Path
$images=@(
 @{name='app';image='opspilot-full/app:f19';archive='f19-app-image.tar'},
 @{name='redis';image='opspilot-full/redis:f15';archive='redis-final.tar'},
 @{name='postgres';image='opspilot-full/postgres:f01';archive='f17-postgres.tar'},
 @{name='manager';image='opspilot-full/manager:f17';archive='f17-manager.tar'}
)
$results=@()
foreach($item in $images){
 $expected=(& docker image inspect $item.image --format '{{.Id}}').Trim()
 if($LASTEXITCODE){throw 'Image identity unavailable'}
 # Reuse archives only after hashing their actual config bytes against the runtime ID.
 $probe="import tarfile,json,hashlib; t=tarfile.open('/cache/"+$item.archive+"'); m=json.load(t.extractfile('manifest.json')); assert len(m)==1; print('sha256:'+hashlib.sha256(t.extractfile(m[0]['Config']).read()).hexdigest())"
 $actual=(& docker run --rm --network none --user 0 --entrypoint python -v "${cache}:/cache:ro" opspilot-full/app:f19 -c $probe).Trim()
 if($LASTEXITCODE -or $actual -ne $expected){throw "Cached archive does not match current image: $($item.name)"}
 & docker run --rm --memory 768m -v "${reports}:/reports" -v "${cache}:/root/.cache/trivy" $scanner --quiet image --db-repository public.ecr.aws/aquasecurity/trivy-db:2 --timeout 20m --input ("/root/.cache/trivy/"+$item.archive) --scanners vuln --format json --output ("/reports/"+$item.name+'-image.json')
 $exit=$LASTEXITCODE
 if($exit){throw "Fresh image scan unavailable: $($item.name), exit $exit"}
 $raw=Get-Content -Raw (Join-Path $reports ($item.name+'-image.json')) | ConvertFrom-Json
 $blocking=@($raw.Results | ForEach-Object {$_.Vulnerabilities} | Where-Object {$_ -and $_.Severity -in @('HIGH','CRITICAL')})
 $results+=@{name=$item.name;image=$item.image;id=$expected;archive_config_verified=$true;high_critical=$blocking.Count}
}
& docker run --rm --memory 768m -u root -v "${reports}:/reports" opspilot-full/tests:f19 uv tool run pip-audit==2.10.1 --path /app/.venv/lib/python3.12/site-packages --format json --output /reports/python-audit.json
$auditExit=$LASTEXITCODE
$checks=@{
 recorded_at=[DateTime]::UtcNow.ToString('o');scanner=$scanner;images=$results
 python_audit_exit=$auditExit;passed=($auditExit -eq 0 -and @($results | Where-Object {$_.high_critical -gt 0}).Count -eq 0)
 scope='F21 runtime images and test Python dependencies; no web or IdP runtime was started by this lab. Existing archives verified against actual image config hashes; fresh advisory scan.'
}
$checks | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $reports 'checks.json')
if(-not $checks.passed){throw 'Security findings retained; no passing claim'}
Write-Output 'F21 image and Python dependency gates passed'
