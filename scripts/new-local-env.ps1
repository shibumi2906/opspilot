# Full worktree compatibility entrypoint. MVP retains its original script.
param([string]$OutputPath = '.env')
& (Join-Path $PSScriptRoot 'new-full-env.ps1') -OutputPath $OutputPath
