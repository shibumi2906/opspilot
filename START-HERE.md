# Продолжение OpsPilot Full

Обновлено 7 ноября 2026 года. Рабочая папка: **C:\Users\user\Desktop\code\Ops**.
Это самостоятельный Git-репозиторий, не ссылка на скрытый worktree.
Сначала откройте эту папку как workspace в редакторе/Codex.

## Текущее состояние

- Ветка: `codex/opspilot-full`. F16: `6330f32`; F17: `017b68b`; F18 — отдельный локальный stage commit (subject в tracker).
- F13: `2fe6613`; F14: `be246d7`; F12: `abfaf76`.
- F01–F18 завершены; **F18 adapter platform/signed ingress принят**; F19–F24 не начаты.
  Перед новым этапом используйте текущий HEAD и канонический tracker.
- Схема Full: `0019_adapters`. Pinned graphs v1/v2, DTO/state1, checkpoint SDK9 сохранены.
- [Канонический tracker](docs/full-version-status.md).
- [Спецификация Full](OpsPilot_Full_Project_Specification.md).
- [План безопасности SEC-01–12](docs/security/asvs-l2-implementation-plan.md).
- [Backlog 253 требований](docs/security/asvs-l2-requirement-backlog.json).
- Полный ASVS L2: **NOT_MET**; завершение F18 означает только принятый scope F18.

## Разделение папок

MVP остаётся в `C:\Users\user\Desktop\code\AI Incident & Operations Agent`,
ветка main, HEAD `f9f8d79`. Он не переносится в Ops и не изменяется.

Исходный Full сохранён в
`C:\Users\user\.codex\worktrees\opspilot-full-f01\AI Incident & Operations Agent`.
Продолжать работу нужно здесь, в Ops. Две копии нельзя параллельно запускать с одним
Compose project. Удалять старый worktree до проверки bind mounts нельзя.

Локатор: `.tools/opspilot-full-workspace.json`. Он содержит явный `mvp_path`.
У самостоятельного репозитория путь MVP нельзя определять как родителя .git.
F15 runner принимает `-MvpPath` и умеет читать этот локатор.

## Что перенесено

Весь tracked код, миграции, спецификации, tests/evidence, документация и история Git.
Локально, в игнорируемые файлы: существующий .env, service/grant keys, независимые dev/test
Redis secrets, исходные fingerprints MVP, последний native TLS lab и private IdP backup.
Проверка копирования — `.tools/local-copy-manifest.json`; значения секретов не выводятся.

Python .venv создан заново по uv.lock; web/node_modules устанавливается по package-lock.json.
Окружение не должно импортировать исходники из прежнего скрытого worktree.
Локальный uv: `.tools/bin/uv.exe`. .env и .tools запрещено добавлять в Git принудительно.
Не генерируйте повторно .env, ключи или пароли поверх существующих.

## Проверить окружение

PowerShell, из этой папки:

~~~powershell
git status --short
git log -5 --oneline
.\scripts\check-ops-workspace.ps1 -CheckMvp
docker compose --env-file .env -p opspilot-full -f compose.full.yaml -f compose.full.f17-local.yaml -f compose.full.f18-local.yaml ps
~~~

UI: http://127.0.0.1:8091
API health: http://127.0.0.1:8011/health
OIDC: http://127.0.0.1:8181
Diagnostics: авторизованный пункт Diagnostics в UI; collector/legacy Jaeger не публикуют порты.

Переподключение к Ops выполнено: runtime image IDs и counts/SHA256 всех 12 прежних таблиц
совпали, миграции и seed не запускались. Реальный OIDC/scripted worker/refresh smoke прошёл.
Действующие bind mounts указывают на Ops, исходный Full worktree сохранён.
[Результаты подготовки](docs/ops-workspace-checks.json).

Пароли находятся только в локальном .env. LLM_MODE остаётся scripted.
Перед сборками/миграциями запускайте check-full-isolation.ps1 с явным MVP path.
Результаты workspace-проверок хранятся под .tools, отдельно от принятого F15 evidence.

Если зависимости потребуется создать заново:

~~~powershell
.\.tools\bin\uv.exe sync --frozen --python 3.12
npm.cmd --prefix web ci --no-audit --no-fund
~~~

## Работа с уже существующим Full

Обычная проверка или запуск без rebuild и без seed/migrations:

~~~powershell
docker compose --env-file .env -p opspilot-full -f compose.full.yaml -f compose.full.f17-local.yaml -f compose.full.f18-local.yaml up -d --wait --no-build postgres redis oidc collector mcp api worker worker2 web
~~~

F17 использует проверенный логический restore в новом PostgreSQL16 volume.
Исходный `opspilot-full_pgdata` сохранён с прежним образом `postgres:f16-before-f17`.
Не подключайте старый физический volume к новому libc runtime. Local override выбирает
проверенный volume через ignored `FULL_F17_PG_VOLUME`. Перед запуском обновите часовые
manager tokens: `.venv/Scripts/python.exe scripts/setup-full-f17-manager.py --local`.
Setup сохраняет ключи. [F17 operations](docs/full/f17-operations.md).

Существующие volumes, пользователи, grants и данные используются повторно.
Docker volumes остаются в Docker Desktop; файлы БД не экспортировались в папку Ops.
Не выполняйте setup/seed/bootstrap identity из исторического MVP README.
Изменение кода приложения потребует обычного отдельного build и stage checks.

## Принятые проверки F15

[Измеренные результаты](docs/full/evidence/f15/checks.json):
backend402/11 dedicated skips, browser22, queue5, fencing3, provider crash1,
Redis stop/recreate1, native TLS8+Redis6+MFA14+IdP policy4, scripted eval12/12.
App/web/Redis raw HIGH/CRITICAL0; IdP raw4 с exact-image applicable0 proof.
Это исторические результаты F15, не новое выполнение в этой папке.
Reference helpers для source/image/secret checks сохранены локально в .tools/reference-helpers.
Адаптированный .tools/verify-workspace-secrets.py пишет результат в .tools/verification,
не перезаписывая исторические отчёты F15.

Команды полного повторного прогона при необходимости:

~~~powershell
.\scripts\test-full-f15.ps1 -MvpPath 'C:\Users\user\Desktop\code\AI Incident & Operations Agent'
.\scripts\test-full-f15-tls.ps1 -SkipBuild
~~~

Эти команды ресурсоёмкие и меняют тестовые evidence/контейнеры.
Они не запускались повторно только ради копирования workspace.

## Docker и отдельный старый проект

Desktop4.97.0 / Engine29.9.2 установлены и работают. Старый сбой установщика прошёл после
освобождения места; перед тяжёлыми сборками проверяйте свободное место на C:.
Данные Docker, контейнеры и образы сохранены; WSL package отдельно не обновлялся.
Полный image inventory сравнивается с `docker image ls -a`.

pinui-rag-api — другой проект. Он ссылается на удалённый VEKTOR.BD:
восстановилась лишь пустая bind-папка data, отсутствует index-manifest.json и compose-файл.
Его FileNotFoundError не блокирует OpsPilot. Не искать файлы удалённого проекта и не
восстанавливать его в рамках продолжения OpsPilot. Сведения о host update — в .tools.

## Запрос для продолжения

F18 завершён. Для следующего этапа нужен отдельный запрос пользователя с явным scope.
F19–F24 не начинать автоматически; canonical tracker определяет очередь и обязательные gates.
Один этап — отдельный локальный commit, без push. Исторические отчёты ниже не переписывать.

## Принятый F16

[Итоговые checks](docs/full/evidence/f16/checks.json): backend422/11 dedicated skips,
browser23, queue5, fencing3, provider crash1, Redis restart1, native TLS8/collector12/
Redis6/MFA14/IdP policy4, eval12/12. Source matches131 Python и38 UI/browser files.
Dev Full уже обновлён до0017_observability с сохранением legacy data всех12 таблиц.
[Контракты](docs/full/f16-security-contracts.md), [runbook](docs/full/f16-observability-runbook.md).
F17 не начат, полный L2 NOT_MET. Следующий этап требует отдельного запроса.

Telemetry credentials в ignored .tools/observability и observability-test; native TLS lab
security-f16-final имеет отдельные CA/keys. Не вращать/перегенерировать существующие ключи.
Collector journal и sealed head находятся в разных named volumes; при corruption сохранять
обе копии и восстанавливать только проверенный paired backup под исходным key. Нельзя
удалять journal ради зелёного health. Роли API/probe читают metadata, worker/MCP только пишут.

Повторная полная проверка: scripts/test-full-f16.ps1; hardened: scripts/test-full-f16-tls.ps1.
Для обычного запуска существующего dev не запускать seed/bootstrap и повторную миграцию.


## Принятый F17

[Итоговый evidence](docs/full/evidence/f17/README.md), [проверки](docs/full/evidence/f17/checks.json),
[операции](docs/full/f17-operations.md). Full Pilot/F18–F24 и полный ASVS L2 остаются NOT_MET.
После замены API container перезапустите `web`, чтобы Nginx обновил upstream DNS.
Manager tokens обновляются явным setup --local, максимум1 час; ключи setup сохраняет.
Повторный запуск one-time deploy helper после schema0018 запрещён preflight до остановки сервисов.

## Принятый F18 — текущее состояние

[Evidence](docs/full/evidence/f18/README.md), [checks](docs/full/evidence/f18/checks.json),
[contracts](docs/full/f18-security-contracts.md), [operations](docs/full/f18-operations.md).
Backend486/44 dedicated skips, transport33, unit200, browser24, queue5/fencing3, eval12/12;
native TLS8/collector12/Redis6/MFA14/IdP4 и новый positive ingress/verify-full DB/CLI; raw H/C0
во всех6 runtime images.253 ASVS inherited rows intact, scoped reviews102/primary contributions5;
полный ASVS L2 и Pilot NOT_MET, F19–F24 не начаты.

Существующий Full уже на0019:48 legacy tables/columns/counts/SHA256 сохранены после backup/restore,
default adapter registry пустой. Ingress-worker не имеет business/MCP/manager credentials или key
mounts. Synthetic simulator optional и не включён по умолчанию; в production он запрещён.
Для обычного рестарта без seed/migration используйте оба local overrideF17/F18 и сначала:

```powershell
.venv/Scripts/python.exe scripts/setup-full-f18.py --local
```

Это сохраняет dev keys/credentials и обновляет только часовые service tokens. Старый F17-only
setup не обновляет connector-purpose tokens F18. Не повторять one-time deploy helper после0019:
он откажет preflight до shutdown. Original Full PG volume не подключать к новому libc runtime.

F18 checks: scripts/test-full-f18.ps1 (default r4/subnet21), test-full-f18-regression.ps1
(отдельные backend и fresh browser/process DB), test-full-f18-tls.ps1 (subnet23). Labs запускать
последовательно. Fresh networks проверяются на overlap; сохранившиеся старые сети не удалять ради
автоматического address pool. MVP unchanged, no push/paid calls/vendor writes/production deployment.
