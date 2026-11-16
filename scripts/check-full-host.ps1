param([Parameter(Mandatory=$true)][string]$ReportPath,[switch]$OnlineUpdateAssessment)
# Read-only host assessment. No key protectors/passwords, settings changes or installs.
$ErrorActionPreference='Stop'
trap {
 $failure=@{checked_at_utc=[DateTime]::UtcNow.ToString('o');status='failed';settings_changed=$false;error_type=$_.Exception.GetType().FullName;error_hresult=$_.Exception.HResult;script_line=$_.InvocationInfo.ScriptLineNumber}
 if($null -ne $admin){$failure.administrator=$admin}
 $failure | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
 exit 1
}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=[Security.Principal.WindowsPrincipal]::new($identity)
$admin=$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$result=[ordered]@{checked_at_utc=[DateTime]::UtcNow.ToString('o');administrator=$admin;settings_changed=$false}
if(-not $admin){throw 'An elevated Windows process is required for this read-only assessment'}
$os=Get-CimInstance Win32_OperatingSystem
$build=Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
$result.os=@{caption=$os.Caption;version=$os.Version;build=$os.BuildNumber;ubr=$build.UBR;display_version=$build.DisplayVersion}
try {
 $volume=Get-BitLockerVolume -MountPoint 'C:' -ErrorAction Stop
 $result.storage=@{mount_point='C:';volume_status=[string]$volume.VolumeStatus;protection_status=[string]$volume.ProtectionStatus;encryption_method=[string]$volume.EncryptionMethod;encryption_percentage=$volume.EncryptionPercentage;recovery_protector_present=(@($volume.KeyProtector | Where-Object KeyProtectorType -eq 'RecoveryPassword').Count -gt 0)}
}catch{$result.storage=@{status='unverified';error_hresult=$_.Exception.HResult}}
try {
 $mp=Get-MpComputerStatus
 function UtcStamp($value){if($null -ne $value){([DateTime]$value).ToUniversalTime().ToString('o')}else{$null}}
 $result.defender=@{antivirus_enabled=$mp.AntivirusEnabled;real_time_enabled=$mp.RealTimeProtectionEnabled;signatures_updated_utc=(UtcStamp $mp.AntivirusSignatureLastUpdated);quick_scan_end_utc=(UtcStamp $mp.QuickScanEndTime);full_scan_end_utc=(UtcStamp $mp.FullScanEndTime)}
}catch{$result.defender=@{status='unverified';error_hresult=$_.Exception.HResult}}
try{$tpm=Get-Tpm; $result.tpm=@{present=$tpm.TpmPresent;ready=$tpm.TpmReady;enabled=$tpm.TpmEnabled}}catch{$result.tpm=@{status='unverified';error_hresult=$_.Exception.HResult}}
$result.hotfixes=@(Get-HotFix | ForEach-Object {@{id=$_.HotFixID;installed_on=[string]$_.InstalledOn}})
try {
 $session=New-Object -ComObject Microsoft.Update.Session
 $searcher=$session.CreateUpdateSearcher()
 $searcher.Online=[bool]$OnlineUpdateAssessment
 $search=$searcher.Search("IsInstalled=0 and IsHidden=0 and Type='Software'")
 $updates=@()
 for($i=0;$i -lt $search.Updates.Count;$i++){
  $item=$search.Updates.Item($i)
  $updates+=@{title=$item.Title;kb=@($item.KBArticleIDs);downloaded=$item.IsDownloaded}
 }
 $result.update_assessment=@{status='completed';online=[bool]$OnlineUpdateAssessment;result_code=[int]$search.ResultCode;pending=$updates;fresh_online_assessment=[bool]$OnlineUpdateAssessment;installs_performed=$false}
}catch{$result.update_assessment=@{status='unverified';online=[bool]$OnlineUpdateAssessment;error_hresult=$_.Exception.HResult;installs_performed=$false}}
$vhdRoot=Join-Path $env:LOCALAPPDATA 'Docker\wsl'
$result.docker_storage=@{vhd_on_c_confirmed=$false}
if(Test-Path -LiteralPath $vhdRoot){
 $vhd=@(Get-ChildItem -LiteralPath $vhdRoot -Filter '*.vhdx' -File -Recurse -ErrorAction SilentlyContinue)
 $result.docker_storage=@{vhd_on_c_confirmed=($vhd.Count -gt 0);vhd_count=$vhd.Count}
}
$full=[IO.Path]::GetFullPath($ReportPath)
$parent=Split-Path -Parent $full
if(-not(Test-Path -LiteralPath $parent)){New-Item -ItemType Directory -Path $parent | Out-Null}
if(Test-Path -LiteralPath $full){throw 'Existing host report preserved; choose a fresh report path'}
$result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $full -Encoding UTF8
