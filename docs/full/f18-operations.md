# F18: локальные операции

F18 — synthetic adapter platform и подписанный observation ingress. MCP не получает новых
vendor tools, webhook не является approval и не запускает business write. Full Pilot/ASVS L2 NOT_MET.

Обычный запуск уже мигрированного Full (без seed/bootstrap/migration):

```powershell
.venv/Scripts/python.exe scripts/setup-full-f18.py --local
docker compose --env-file .env -p opspilot-full -f compose.full.yaml -f compose.full.f17-local.yaml -f compose.full.f18-local.yaml up -d --wait --no-build postgres redis oidc collector mcp api worker worker2 ingress-worker web
```

Setup сохраняет dev credentials/ring/CA, обновляет только часовые service tokens и не включает
config. Test state отдельно в `.tools/f18-*`; dev в `.tools/f18-*-dev`. Manager root/unseal/CA-key
остаются на host, не в app mounts. Не выводить fixture/token/DSN или `docker compose config` в логи.
Реестр после deploy пустой: прежний scripted Core работает с прежними fixtures.

Переход с0018 выполняет **один раз** `scripts/deploy-full-f18-local.ps1`: MVP prerequisite,
проверка точного PG image/verified logical volume и subnet overlap до остановки сервисов, drain,
fingerprint всех таблиц domain/workflow/identity/checkpoints, encrypted offline backup и fresh
restore без сети, migration0019, отдельное provision ops_ingress, сравнение всех прежних columns,
restart/health и OIDC/scripted/refresh smoke. Ни seed, ни import в оригинальный Full/MVP volume.
Повторный запуск после0019 останавливается preflight до shutdown. Recovery artifacts сохраняются
в ignored `.tools/f18-full-*`; restore-контейнер остановлен, volume и encrypted archive сохранены.
Это локальный upgrade proof; production/off-host recovery остаётся F23.

Сохранённый `opspilot-full_pgdata` нельзя подключать к Alpine runtime. Dev продолжает использовать
`FULL_F17_PG_VOLUME` из private .env и overrideF17. F18 не меняет libc/PostgreSQL image.

Опциональный simulator запускается только явным профилем:

```powershell
docker compose --env-file .env -p opspilot-full -f compose.full.yaml -f compose.full.f17-local.yaml -f compose.full.f18-local.yaml --profile f18-simulator up -d --wait adapter-simulator
```

Он доступен MCP только через отдельную internal network `10.245.22.0/24`, без host port.
Credentials dev независимы от test. Для использования admin с действующей session/recent MFA
создаёт config через `/api/v2/admin/adapters/{connectorUUID}` с expected_version0, kind simulator,
mapping_version1, существующими customer/integration и origin `https://adapter-simulator:8443`.
Flags read_enabled/ingress_enabled по умолчанию false. При добавлении tenant operator явно задаёт trusted `RECOVERY_TENANTS` у ingress-worker (по умолчанию два local fixture tenants); callback/model не управляет этим списком. Server вычисляет credential refs/hash;
secret values/paths в API не принимаются. Operator отдельно provision manager records и exact ACL
для connector; включение config не выдаёт manager-доступ к произвольной identity. Локальный helper
разрешает только два deterministic identities из `tests/f18_cases.py`, не включает их в DB.

Ingress endpoint local: `http://127.0.0.1:8091/ingress/v1/{tenant}/{connector}`.
Native TLS edge проверяется отдельным lab; production endpoint не создан. Только POST/applicationJSON,
без cookie/bearer/query/compression. HMAC headers: X-Ops-Timestamp (DB clock ±300s), X-Ops-Key-Id и
X-Ops-Signature (lowercase64hex). MAC input — `opspilot-ingress-v1\n{tenant}\n{connector}\n{stamp}\n`
плюс исходные body bytes. Payload: event_id UUID, monotonic sequence, mapped customer_id/integration_id,
status enum healthy/degraded/unavailable/unknown, aware observed_at (не старше24h и не далее30s вперёд).
Receipt+job commit предшествует202; точный retry200; изменённый body под тем же event_id409.
Не переписывать event identity при timeout; подписать тот же raw body с новым timestamp при необходимости.

Пределы: body16KiB, slot4, rate60/min, pending100/connector и1000 global; retained10000/connector,
100000 global. При429 не удалять receipts ради возобновления: сначала проверить pending worker и
metadata/audit, затем согласовать отдельную archive/anti-replay migration. Отсутствующий/expired/revoked
manager token, bad TLS или неизвестный scope дают fail-closed. Breaker после3 ошибок открыт30s;
get_credential_status возвращает unknown, не выводит срок из HTTP401.

При компрометации: disable config (CAS), revoke service token/kid, operator CAS новый ring с explicit
metadata, проверить callbacks и audit, refresh scoped token и затем enable. Retirement действует на
следующий fetch; bounded in-flight verifier может завершиться в пределах2s. Disable сериализован
с admission/processing и является барьером; pending jobs quarantine, существующие receipts остаются.

Воспроизводимые checks без vendor/paid calls:

```powershell
./scripts/test-full-f18.ps1
.venv/Scripts/python.exe scripts/test-full-f18-manager.py
./scripts/test-full-f18-regression.ps1 -SkipBuild
./scripts/test-full-f18-tls.ps1 -SkipBuild
```

Manager drill использует r4/subnet21 и требует поднятого соответствующего test profile; стандартный
contract runner по завершении останавливает свой profile. Для drill используйте
`test-full-f18.ps1 -Project opspilot-full-test-f18-r4 -Subnet 21 -StartOnly -SkipBuild`. TLS/регрессию запускать последовательно: на16GiB host параллельные labs
вызвали memory pressure и зависание Engine; восстановлен разрешённым restart без reset/удаления.
Тесты/manager profiles остановить после проверки; не останавливать другие проекты.
