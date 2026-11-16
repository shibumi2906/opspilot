param([Parameter(Mandatory=$true)][string]$OwnerSid,[switch]$UpdateOwned,[switch]$LeaveDisabled,[switch]$StartVerification)
# Only these two uniquely named tasks. Interactive owner; no stored Windows password.
$ErrorActionPreference='Stop'
$workspace=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $workspace
$python=Join-Path $workspace '.venv\Scripts\pythonw.exe'
$script=Join-Path $workspace 'scripts\full_backup.py'
$config=Join-Path $workspace '.tools\full-backup-operations\config.json'
$record=Get-Content -LiteralPath $config -Raw | ConvertFrom-Json
if($record.project -ne 'opspilot-full-test-f23-recovery4'){throw 'Schedule is restricted to the reviewed recovery4 pilot'}
if(-not(Test-Path -LiteralPath $python)){throw 'Existing project Python environment required'}
$principal=New-ScheduledTaskPrincipal -UserId $OwnerSid -LogonType Interactive -RunLevel Limited
$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -MultipleInstances Queue -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 10)
$names=@()
foreach($mode in @('backup','refresh-identities')){
 $name=if($mode -eq 'backup'){'OpsPilot-Full-Backup-Recovery4'}else{'OpsPilot-Full-Secrets-Recovery4'}
 $arguments=('"{0}" {1} --config "{2}"' -f $script,$mode,$config)
 $action=New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $workspace
 if($mode -eq 'backup'){
  $triggers=@((New-ScheduledTaskTrigger -Daily -At '03:00'),(New-ScheduledTaskTrigger -Daily -At '15:00'),(New-ScheduledTaskTrigger -AtLogOn -User $OwnerSid))
 }else{
  $triggers=@((New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Minutes 30)),(New-ScheduledTaskTrigger -AtLogOn -User $OwnerSid))
 }
 $existing=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
 if($existing){
  $allowedExecutables=@($python,(Join-Path $workspace '.venv\Scripts\python.exe'))
  if($existing.Actions.Count -ne 1 -or $existing.Actions[0].Execute -notin $allowedExecutables -or $existing.Actions[0].Arguments -ne $arguments){throw 'Existing task has a different action; preserved without replacement'}
  if(-not $UpdateOwned){throw 'Owned task already exists; inspect or explicitly update it'}
  Disable-ScheduledTask -TaskName $name | Out-Null
  if([string]$existing.State -eq 'Running'){throw 'Existing task is running; allow it to finish before updating'}
 }
 $task=New-ScheduledTask -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Description 'OpsPilot isolated scripted recovery4 only. Keys preserved. No provider dispatch or source migrations. Requires logged-in owner and Docker Desktop.'
 Register-ScheduledTask -TaskName $name -InputObject $task -Force:$UpdateOwned | Out-Null
 if($LeaveDisabled){Disable-ScheduledTask -TaskName $name | Out-Null}
 $names+=$name
}
@{registered_at_utc=[DateTime]::UtcNow.ToString('o');tasks=$names;project=$record.project;stored_windows_password=$false;requires_logged_in_owner=$true;backup_local_times=@('03:00','15:00');refresh_interval_minutes=30;enabled=(-not $LeaveDisabled);background_executable='pythonw.exe'} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath '.tools\full-backup-operations\schedule-installed.json' -Encoding UTF8
if($StartVerification){if($LeaveDisabled){throw 'Cannot verify a disabled task'};Start-ScheduledTask -TaskName 'OpsPilot-Full-Backup-Recovery4'}
