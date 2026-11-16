param([Parameter(Mandatory=$true)][string]$Directory)
# Prepare a recovery protector and an owner-readable temporary copy. Never enable encryption.
$ErrorActionPreference='Stop'
$workspace=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$target=[IO.Path]::GetFullPath($Directory)
$expected=Join-Path $workspace '.tools\host-recovery'
if($target -ne $expected){throw 'Only the explicitly owned private recovery directory is allowed'}
New-Item -ItemType Directory -Path $target -Force | Out-Null
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $target /inheritance:r /grant:r ('*'+$sid+':(OI)(CI)F') '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' /q | Out-Null
if($LASTEXITCODE -ne 0){throw 'Private recovery ACL failed'}
$report=Join-Path $target 'preparation-status.json'
try {
 $volume=Get-BitLockerVolume -MountPoint 'C:'
 if([string]$volume.VolumeStatus -ne 'FullyDecrypted'){throw 'Unexpected volume state; preserve existing protection'}
 $keyfile=Join-Path $target 'BitLocker-C-recovery.txt'
 if(Test-Path -LiteralPath $keyfile){throw 'Existing recovery file preserved; no protector change'}
 $recovery=@($volume.KeyProtector | Where-Object KeyProtectorType -eq 'RecoveryPassword')
 $added=$false
 if($recovery.Count -eq 0){
  Add-BitLockerKeyProtector -MountPoint 'C:' -RecoveryPasswordProtector | Out-Null
  $added=$true
  $volume=Get-BitLockerVolume -MountPoint 'C:'
  $recovery=@($volume.KeyProtector | Where-Object KeyProtectorType -eq 'RecoveryPassword')
 }
 if($recovery.Count -ne 1 -or $recovery[0].RecoveryPassword -notmatch '^\d{6}(-\d{6}){7}$'){throw 'Recovery protector cannot be safely selected'}
 $content="BitLocker recovery key for C:`r`nProtector ID: $($recovery[0].KeyProtectorId)`r`nRecovery password: $($recovery[0].RecoveryPassword)`r`n`r`nTemporary local copy. Copy to paper or an independent device before encryption.`r`nDo not send this file or password to chat, Git, logs or support.`r`n"
 $bytes=[Text.Encoding]::UTF8.GetBytes($content)
 $stream=[IO.File]::Open($keyfile,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
 try{$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
 $after=Get-BitLockerVolume -MountPoint 'C:'
 @{prepared_at_utc=[DateTime]::UtcNow.ToString('o');passed=$true;recovery_file_created=$true;protector_added=$added;encryption_enabled=$false;volume_status=[string]$after.VolumeStatus;protection_status=[string]$after.ProtectionStatus;awaiting_off_disk_copy=$true} | ConvertTo-Json | Set-Content -LiteralPath $report -Encoding UTF8
}catch{
 @{prepared_at_utc=[DateTime]::UtcNow.ToString('o');passed=$false;encryption_enabled=$false;error_type=$_.Exception.GetType().FullName;error_hresult=$_.Exception.HResult;script_line=$_.InvocationInfo.ScriptLineNumber} | ConvertTo-Json | Set-Content -LiteralPath $report -Encoding UTF8
 exit 1
}
