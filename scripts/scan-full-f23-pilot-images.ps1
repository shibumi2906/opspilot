param(
 [ValidatePattern('^opspilot-full-test-f23-[a-z0-9]+$')][string]$Project='opspilot-full-test-f23-recovery3',
 [ValidatePattern('^[a-z0-9]+$')][string]$Attempt='r1',
 [string]$ImageOverrides
)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$manifest=Get-Content ".tools/$Project/release-manifest.json" -Raw | ConvertFrom-Json
if($ImageOverrides){
 $overrides=Get-Content -LiteralPath $ImageOverrides -Raw | ConvertFrom-Json
 foreach($entry in $overrides.PSObject.Properties){
  if($entry.Name -notin @('web','postgres','redis','oidc','manager') -or $entry.Value -notmatch '^sha256:[a-f0-9]{64}$'){throw 'Explicit runtime image digest overrides required'}
  $manifest.images.($entry.Name)=$entry.Value
 }
}
$report="docs/full/evidence/f23/local-pilot-20261116/images-$Attempt"
$archives=".tools/f23-scans/$Project-$Attempt"
New-Item -ItemType Directory $report | Out-Null
New-Item -ItemType Directory $archives | Out-Null
$cache=(Resolve-Path .tools/trivy-cache).Path
$scanner='aquasec/trivy@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c'
$reportPath=(Resolve-Path $report).Path
$archivePath=(Resolve-Path $archives).Path
& docker run --rm --memory 768m -e GOMEMLIMIT=600MiB -v "${cache}:/root/.cache/trivy" $scanner image --quiet --download-db-only --db-repository public.ecr.aws/aquasecurity/trivy-db:2 --timeout 5m *>> "$archives/scan.log"
if($LASTEXITCODE){throw 'Fresh vulnerability DB download failed; see ignored scan.log'}
Copy-Item -LiteralPath "$cache/db/metadata.json" -Destination "$report/db-metadata.json"
$counts=@()
$blocking=@()
foreach($name in @('app','web','postgres','redis','oidc','manager')){
 $digest=$manifest.images.$name
 if($digest -notmatch '^sha256:[a-f0-9]{64}$'){throw 'Pinned image ID required'}
 & docker save $digest -o "$archives/$name.tar" *>> "$archives/scan.log"
 if($LASTEXITCODE){throw "Image archive failed: $name"}
 & docker run --rm --memory 768m -e GOMEMLIMIT=600MiB -v "${cache}:/root/.cache/trivy" -v "${archivePath}:/images:ro" -v "${reportPath}:/reports" $scanner image --quiet --skip-db-update --input "/images/$name.tar" --scanners vuln --timeout 10m --format json --output "/reports/$name.json" *>> "$archives/scan.log"
 if($LASTEXITCODE){throw "Image scan failed: $name; see ignored scan.log"}
 $data=Get-Content "$report/$name.json" -Raw | ConvertFrom-Json
 if($data.Metadata.ImageID -ne $digest){throw "Scanned image identity mismatch: $name"}
 $findings=@($data.Results | ForEach-Object { $_.Vulnerabilities } | Where-Object { $_ -and $_.Severity -in @('HIGH','CRITICAL') })
 $counts+=@{image=$name;image_id=$digest;high_critical=$findings.Count}
 foreach($finding in $findings){$blocking+=@{image=$name;id=$finding.VulnerabilityID;package=$finding.PkgName;installed=$finding.InstalledVersion;fixed=$finding.FixedVersion}}
 Write-Output "$name high/critical: $($findings.Count)"
}
$gate=@{scanned_at_utc=[DateTime]::UtcNow.ToString('o');project=$Project;scanner=$scanner;images=$counts;blocking=$blocking;passed=($blocking.Count -eq 0);full_asvs_l2='NOT_MET'}
$gate | ConvertTo-Json -Depth 8 | Set-Content "$report/gate.json"
if($blocking.Count){throw 'Applicable runtime image findings block release; all raw reports retained'}
Write-Output 'All six exact runtime images have zero raw HIGH/CRITICAL findings'
