param([ValidatePattern('^opspilot-full-test-[a-z0-9-]+$')][string]$Project='opspilot-full-test-f15-acceptance')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$c=@('compose','--env-file','.env','-p',$Project,'-f','compose.full.yaml','-f','compose.full.test.yaml')
$query="SELECT json_build_object('attempts',(SELECT count(*) FROM workflow.provider_attempts),'held_tokens',(SELECT COALESCE(sum(held_tokens),0) FROM workflow.provider_attempts),'source_units',(SELECT COALESCE(sum(used),0) FROM workflow.source_budgets))"
$before=(& docker @c exec -T postgres psql -U ops_migration -d opspilot_full_test -Atc $query | ConvertFrom-Json)
if($LASTEXITCODE){throw 'Durable baseline unavailable'}
& docker @c stop redis
if($LASTEXITCODE){throw 'Redis outage setup'}
try {
 & docker @c run --rm --no-deps -e TEST_F15_REDIS_DOWN=1 tests python -m pytest -p no:cacheprovider -q tests/integration/test_governance.py -k real_redis_outage_bounded_direct_read
 if($LASTEXITCODE){throw 'Real Redis outage check'}
} finally {
 & docker @c up -d --wait --force-recreate redis
 if($LASTEXITCODE){throw 'Redis restoration'}
}
$after=(& docker @c exec -T postgres psql -U ops_migration -d opspilot_full_test -Atc $query | ConvertFrom-Json)
if($LASTEXITCODE -or $before.attempts -ne $after.attempts -or $before.held_tokens -ne $after.held_tokens -or $after.source_units -lt $before.source_units){throw 'Durable counters changed/refunded across Redis restart'}
@{passed=$true;before=$before;after=$after;cache_container_recreated=$true;redis_persistence=$false;database_counters_refunded=$false} | ConvertTo-Json -Depth 5 | Set-Content docs/full/evidence/f15/redis-restart.json
