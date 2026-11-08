param([ValidatePattern('^opspilot-full-test-f21-[a-z0-9-]+$')][string]$Project='opspilot-full-test-f21-r4')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$report='docs/full/evidence/f21/load-soak.json'
$faults=@()
foreach($item in @(@{service='mcp';after=6},@{service='redis';after=12},@{service='collector';after=18},@{service='postgres';after=24})){
 $limit=[DateTime]::UtcNow.AddMinutes(35)
 while($true){
  if([DateTime]::UtcNow -gt $limit){throw 'F21 fault schedule timed out'}
  if(Test-Path -LiteralPath $report){
   $state=Get-Content -Raw -LiteralPath $report | ConvertFrom-Json
   if($state.phase -eq 'failed'){throw 'Load failed; no further faults injected'}
   if($state.phase -eq 'soak' -and $state.soak.completed_runs -ge $item.after){break}
  }
  Start-Sleep -Seconds 3
 }
 $container=$Project+'-'+$item.service+'-1'
 $labels=(& docker inspect $container --format '{{index .Config.Labels "com.docker.compose.project"}} {{index .Config.Labels "com.docker.compose.service"}}').Trim()
 if($LASTEXITCODE -or $labels -ne ($Project+' '+$item.service)){throw 'Fault target identity mismatch'}
 $begin=[DateTime]::UtcNow
 & docker stop --time 5 $container | Out-Null
 if($LASTEXITCODE){throw 'F21 stop failed'}
 Start-Sleep -Seconds 6
 & docker start $container | Out-Null
 if($LASTEXITCODE){throw 'F21 recovery start failed'}
 $ready=$false
 $deadline=[DateTime]::UtcNow.AddSeconds(90)
 while([DateTime]::UtcNow -lt $deadline){
  $health=(& docker inspect $container --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}').Trim()
  if($health -in @('healthy','running')){$ready=$true;break}
  Start-Sleep -Seconds 2
 }
 $faults+=@{service=$item.service;started_at_utc=$begin.ToString('o');stopped_seconds=6;health_recovered=$ready;stop_to_health_seconds=([DateTime]::UtcNow-$begin).TotalSeconds;scope='isolated F21 test container only'}
 $faults | ConvertTo-Json -Depth 5 | Set-Content docs/full/evidence/f21/service-outages.json
 if(-not $ready){throw 'F21 service did not recover'}
 Write-Output ('F21 recovered '+$item.service)
}
