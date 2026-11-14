param([string]$Image = "opspilot-full/manager:f17", [switch]$ResolveGoProxyOnHost)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$source=Join-Path $PWD '.tools/manager-build'
New-Item -ItemType Directory -Force $source | Out-Null
$archive=Join-Path $source 'openbao-v2.7.2.tar.gz'
if(-not (Test-Path -LiteralPath $archive)) {
    $cached=Join-Path $PWD '.tools/openbao-v2.7.2.tar.gz'
    if(Test-Path -LiteralPath $cached){Copy-Item -LiteralPath $cached -Destination $archive}
    else {Invoke-WebRequest -Uri 'https://codeload.github.com/openbao/openbao/tar.gz/refs/tags/v2.7.2' -OutFile $archive}
}
if((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne '11B48E34EA1BBAD5DB4044CED904C7F1A4265DA5230551463846C6745E507797'){
    throw 'Pinned manager source checksum mismatch'
}
$buildArguments=@('build')
if($ResolveGoProxyOnHost){
    foreach($hostname in @('proxy.golang.org','storage.googleapis.com')){
        $address=Resolve-DnsName $hostname -Type A -ErrorAction Stop |
            Where-Object IPAddress | Select-Object -First 1 -ExpandProperty IPAddress
        if(!$address){throw "No IPv4 address resolved for $hostname"}
        $buildArguments+=@('--add-host',"$hostname`:$address")
    }
}
$buildArguments+=@('--build-context',"manager-source=$source",'-t',$Image,'-f','infra/secrets-manager/Dockerfile','infra/secrets-manager')
& docker @buildArguments
if($LASTEXITCODE){throw 'Manager security build failed'}
$managerVersion=(& docker run --rm --network none --entrypoint bao $Image version | Out-String).Trim()
if($LASTEXITCODE -or $managerVersion -notmatch '^OpenBao v2\.7\.2\+opspilot-f17\.2$'){
    throw 'Manager executable path/version does not match the reviewed security build'
}
Write-Output 'Reviewed manager binary version and executable path verified.'
