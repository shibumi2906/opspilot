param([Parameter(Mandatory=$true)][string]$MvpPath, [string]$ReportPath = 'docs/full/evidence/f01-isolation.json', [string]$MvpDocumentationHead)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$baseline = Get-Content -Raw .tools/mvp-before.json | ConvertFrom-Json
$historicalHead = $baseline.head
$head = (& git -C $MvpPath rev-parse HEAD).Trim()
if ($MvpDocumentationHead) {
    if ($head -ne $MvpDocumentationHead) { throw 'Unexpected MVP documentation commit' }
    & git -C $MvpPath merge-base --is-ancestor $historicalHead $head
    if ($LASTEXITCODE) { throw 'MVP documentation commit must descend from the baseline' }
    $delta = @(& git -C $MvpPath diff --name-status --no-renames $historicalHead $head)
    if ($LASTEXITCODE -or $delta.Count -ne 1 -or $delta[0] -cne "M`tREADME.md") {
        throw 'MVP documentation commit must modify only the existing README.md'
    }
    $worktree = @(& git -C $MvpPath status --porcelain)
    if ($LASTEXITCODE -or $worktree.Count) { throw 'MVP checkout must be clean' }
    $baseline.head = $head
    $baseline.files.'README.md' = (Get-FileHash -LiteralPath (Join-Path $MvpPath 'README.md')).Hash
}
$changed = @()
foreach ($file in $baseline.files.PSObject.Properties) {
    $target = Join-Path $MvpPath $file.Name
    if (-not (Test-Path -LiteralPath $target) -or (Get-FileHash -LiteralPath $target).Hash -ne $file.Value) {
        $changed += $file.Name
    }
}
$images = @(& docker image ls --filter 'reference=opspilot:*' --format '{{.Repository}}:{{.Tag}} {{.ID}}' | Sort-Object)
if ($LASTEXITCODE) { throw 'Docker image inventory failed' }
$volumes = (& docker volume inspect opspilot_pgdata opspilot-test_pgdata | Out-String)
if ($LASTEXITCODE) { throw 'Docker volume inventory failed' }
$branch = (& git -C $MvpPath branch --show-current).Trim()
if ($changed.Count -or (Compare-Object $baseline.images $images) -or $volumes -ne $baseline.volumes -or $head -ne $baseline.head -or $branch -ne $baseline.branch) {
    throw "MVP fingerprint mismatch: $($changed -join ', ')"
}
& docker run --rm --network none --read-only --user root --mount type=volume,src=opspilot_pgdata,dst=/mvp,readonly --entrypoint python opspilot-full/app:f01 -c "import pathlib,hashlib,json; p=pathlib.Path('/mvp'); print(json.dumps({str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(p.rglob('*')) if f.is_file()},sort_keys=True))" > .tools/mvp-volume-after.json
if ($LASTEXITCODE) { throw 'Read-only volume content check failed' }
if ((Get-Content -Raw .tools/mvp-volume-before.json).Trim() -ne (Get-Content -Raw .tools/mvp-volume-after.json).Trim()) { throw 'MVP volume content changed' }
$result = [ordered]@{
    checked_at_utc = [DateTime]::UtcNow.ToString('o')
    mvp_path = $MvpPath
    mvp_branch = $branch
    mvp_head = $head
    files_including_env = @($baseline.files.PSObject.Properties).Count
    files_unchanged = $true
    image_tags_unchanged = $images
    volume_metadata_unchanged = $true
    mvp_volume_content_unchanged = $true
    mvp_volume_fingerprint_sha256 = ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes((Get-Content -Raw .tools/mvp-volume-after.json).Trim()))).Replace('-', ''))
    note = 'Source/env/media fingerprints captured before Full builds. Volume content baseline captured after initial Full setup; no MVP volume was mounted by Full services. Read-only probe only.'
}
if ($MvpDocumentationHead) { $result['historical_mvp_head'] = $historicalHead }
$result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ReportPath
Write-Output 'MVP tracked files, env, branch/head, image tags, volume metadata and read-only volume content match.'
