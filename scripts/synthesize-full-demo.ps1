param([Parameter(Mandatory=$true)][string]$WorkDirectory)
# Local installed SAPI voice only. No network, keys, cloud TTS or MVP operations.
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$work=[IO.Path]::GetFullPath($WorkDirectory)
if(-not $work.StartsWith((Join-Path $root '.tools\'),[StringComparison]::OrdinalIgnoreCase)){throw 'Use an owned ignored directory under Ops .tools'}
$audio=Join-Path $work 'audio'
New-Item -ItemType Directory -Path $audio -Force | Out-Null
$script=Get-Content -LiteralPath (Join-Path $root 'docs\assets\full\demo-en-script.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$voice=New-Object -ComObject SAPI.SpVoice
$english=@($voice.GetVoices() | Where-Object {$_.GetDescription() -like '*Zira*English*'})
if($english.Count -ne 1){throw 'Expected installed English Zira voice; no cloud fallback'}
$voice.Voice=$english[0]
$voice.Rate=0
$voice.Volume=100
$plan=@()
foreach($scene in $script){
 $file=Join-Path $audio ($scene.key+'.wav')
 if(Test-Path -LiteralPath $file){throw 'Existing narration preserved; choose a fresh work directory'}
 $stream=New-Object -ComObject SAPI.SpFileStream
 $stream.Format.Type=22
 $stream.Open($file,3,$false)
 try{$voice.AudioOutputStream=$stream;[void]$voice.Speak($scene.narration,16)}finally{$stream.Close()}
 $duration=[double]::Parse((& ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 $file),[Globalization.CultureInfo]::InvariantCulture)
 if($LASTEXITCODE -ne 0 -or $duration -lt 1){throw 'Narration duration check failed'}
 $plan+=@{key=$scene.key;chapter=$scene.chapter;role=$scene.role;points=$scene.points;narration=$scene.narration;audio_seconds=$duration;duration_seconds=[Math]::Ceiling($duration/1.08+1)}
 Write-Output ('Local English narration: '+$scene.key)
}
@{voice=$voice.Voice.GetDescription();engine='Windows SAPI (installed offline voice)';narration_tempo=1.08;paid_calls=0;external_tts_requests=0;scenes=$plan} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $work 'plan.json') -Encoding UTF8
