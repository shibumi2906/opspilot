param([string]$Project='opspilot-full-f09-upgrade-release')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$compose=@('compose','--env-file','.env','-p',$Project,'-f','compose.full.yaml','-f','compose.full.test.yaml')
function Check([string[]]$Arguments){ & docker @compose @Arguments; if($LASTEXITCODE){throw 'F09 upgrade check failed'} }
$legacy=(& git show 'f4d84e2:src/opspilot/fixtures/loader.py') -join "`n"
if($LASTEXITCODE){throw 'Pinned pre-F09 fixture source unavailable'}
$legacy=$legacy.Replace('from sqlalchemy.dialects.postgresql import insert', "from sqlalchemy import MetaData, Table`nfrom sqlalchemy.dialects.postgresql import insert")
$legacy=$legacy.Replace('insert(cast(Table, seed_model.__table__))', 'insert(await connection.run_sync(lambda conn: Table(seed_model.__tablename__, MetaData(), schema=seed_model.__table__.schema, autoload_with=conn)))')
$legacy += @'

import asyncio
from opspilot.config import Settings
from opspilot.db.engine import create_engine
async def legacy_main():
    settings=Settings()
    engine=create_engine(settings.database_url('migration'))
    try:
        print(await seed(engine,settings.scenario_clock))
    finally:
        await engine.dispose()
asyncio.run(legacy_main())
'@
$legacy | Set-Content -LiteralPath '.tools/f09-upgrade-legacy.py' -Encoding utf8
try {
 Check @('up','-d','--wait','postgres')
 Check @('run','--rm','admin','alembic','upgrade','0010_security_baseline')
 Check @('run','--rm','-v',"${PWD}:/work:ro",'admin','python','/work/.tools/f09-upgrade-legacy.py')
 Check @('run','--rm','-v',"${PWD}:/work:ro",'admin','python','/work/scripts/check-f09-upgrade.py','before')
 Check @('run','--rm','admin')
 Check @('run','--rm','-v',"${PWD}:/work:ro",'admin','python','/work/scripts/check-f09-upgrade.py','after')
} finally { & docker @compose stop }
