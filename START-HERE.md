# Продолжение OpsPilot Full

Подготовлено 30 октября 2026 года. Рабочая папка: **C:\Users\user\Desktop\code\Ops**.
Это самостоятельный Git-репозиторий, не ссылка на скрытый worktree.
Сначала откройте эту папку как workspace в редакторе/Codex.

## Текущее состояние

- Ветка: `codex/opspilot-full`. Реализация F15: `4733998`.
- F13: `2fe6613`; F14: `be246d7`; F12: `abfaf76`.
- F01–F16 завершены; **F17 не начат**. F16 — отдельный commit после подготовки workspace.
  Перед новым этапом используйте текущий HEAD и канонический tracker.
- Схема Full: `0017_observability`. Pinned graphs v1/v2, DTO/state1, checkpoint SDK9 сохранены.
- [Канонический tracker](docs/full-version-status.md).
- [Спецификация Full](OpsPilot_Full_Project_Specification.md).
- [План безопасности SEC-01–12](docs/security/asvs-l2-implementation-plan.md).
- [Backlog 253 требований](docs/security/asvs-l2-requirement-backlog.json).
- Полный ASVS L2: **NOT_MET**; завершение F16 означает только принятый scope F16.

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
docker compose --env-file .env -p opspilot-full -f compose.full.yaml ps
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
docker compose --env-file .env -p opspilot-full -f compose.full.yaml up -d --wait --no-build postgres redis oidc collector mcp api worker worker2 web
~~~

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

> Выполни только F16 OpsPilot Full в C:\Users\user\Desktop\code\Ops.
> Прочитай AGENTS.md, START-HERE.md, спецификацию и канонический docs/full-version-status.md.
> F15 завершён коммитом 4733998; используй текущий HEAD с подготовкой workspace.
> MVP: C:\Users\user\Desktop\code\AI Incident & Operations Agent.
> Сохрани изоляцию MVP, выполни функциональные и security-задачи F16 (SEC-05 плюс SEC-01/10)
> с целью ASVS L2, проведи проверки, обнови tracker и создай отдельный локальный коммит без push.
> F17 не начинай. Полный L2 не объявляй выполненным без соответствующих будущих gates.

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
