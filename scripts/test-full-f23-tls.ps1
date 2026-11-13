param([string]$Project='opspilot-full-test-f23-tls-r1',[ValidateRange(35,98)][int]$Subnet=55)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if($Project -notmatch '^opspilot-full-test-f23-tls-[a-z0-9]+$'){throw 'Use a dedicated F23 TLS project'}
$mvp=(Get-Content .tools/opspilot-full-workspace.json -Raw | ConvertFrom-Json).mvp_path
& ./scripts/check-full-isolation.ps1 -MvpPath $mvp -MvpDocumentationHead (git -C $mvp rev-parse HEAD) -ReportPath .tools/f23-tls-mvp-before.json
$env:COMPOSE_PARALLEL_LIMIT='1'
$directory=".tools/$Project"
$generator=Get-Content infra/security/generate_local.py -Raw
$generator=$generator.Replace('ROOT = Path(__file__).resolve().parents[2]', 'ROOT = Path.cwd()').Replace('.tools/security-local',$directory)
$generator=$generator.Replace('"name": "opspilot-full-security"','"name": "'+$Project+'"')
$generator=$generator.Replace('"../../docs/security/hardening/evidence:/reports"','"./reports:/reports"')
$generator | Set-Content -Encoding utf8 ".tools/$Project.py"
& .venv/Scripts/python.exe ".tools/$Project.py"
if($LASTEXITCODE){throw 'TLS fixture generation failed'}
New-Item -ItemType Directory "$directory/reports" | Out-Null
$overlay=@{
    networks=@{default=@{ipam=@{config=@(@{subnet="10.245.$Subnet.0/24"})}}}
    services=@{
        api=@{environment=@{LLM_MODE='scripted';OPENAI_API_KEY=''}}
        worker=@{environment=@{LLM_MODE='scripted';OPENAI_API_KEY=''}}
    }
}
$overlay | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 "$directory/f23-overlay.json"
$c=@('compose','-p',$Project,'-f',"$directory/compose.json",'-f',"$directory/f23-overlay.json")
function Invoke-Lab([string[]]$Arguments){
    & docker @c @Arguments *>> "$directory/rehearsal.log"
    if($LASTEXITCODE){throw "F23 TLS step failed: $($Arguments -join ' '). See ignored log."}
}
try {
    Invoke-Lab @('up','-d','--wait','--no-build','postgres','redis','oidc')
    Invoke-Lab @('run','--rm','--no-deps','admin')
    Invoke-Lab @('run','--rm','--no-deps','admin','python','-m','opspilot.cli.seed')
    Invoke-Lab @('run','--rm','--no-deps','admin','python','-m','opspilot.cli.bootstrap_identity')
    Invoke-Lab @('run','--rm','--no-deps','telemetry-init')
    Invoke-Lab @('up','-d','--wait','--no-build','collector','api','mcp','worker','web')
    Invoke-Lab @('restart','web')
    Invoke-Lab @('run','--rm','--no-deps','probe')
    Invoke-Lab @('run','--rm','--no-deps','browser')
} finally {
    Invoke-Lab @('stop')
    & ./scripts/check-full-isolation.ps1 -MvpPath $mvp -MvpDocumentationHead (git -C $mvp rev-parse HEAD) -ReportPath .tools/f23-tls-mvp-after.json
}
