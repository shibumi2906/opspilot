# Продолжение Full — 16 ноября 2026

## Итоговый локальный snapshot перед final push/CI

Самый свежий functional target — **opspilot-full-test-f23-recovery4**, subnets85/86/87,
сейчас running, HTTPS8443/8543 и manager18270. Источник recovery3 остановлен.
Patched web:f23 и postgres:f23 собраны отдельными tags; старые tags/volumes сохранены.
Fresh Trivy **все6 runtime images H/C0**: `local-pilot-20261116/images-r2/gate.json`.
Actual9 runtime containers сверены с этими6 image IDs. Новый полный cold restore
с patched PostgreSQL в fresh volume — **63.88s**,59 hashes matched, committed extra0,
pending new1, restored app/admin MFA passed. Reports:
`docs/full/evidence/f23/local-pilot-20261116/README.md` и final-release-manifest.json.
Manager rotation/revoke/seal/CAS rollback8 checks повторены на recovery4.
Deployment rollback выполнен при drained intake/worker: старый несовместимый API
получил503, pinned current API восстановлен,59 tables unchanged. Sources preserved.

Последние SEC checks:570 public candidate/source artifacts,10 final runtime/log streams,
known-secret matches0/JWT0;253 ASVS rows unchanged. Финальная read-only isolation MVP прошла.
Новые raw image scans r1 (web3/PG19 HIGH) сохранены; r2 их не скрывает.

F22 owner review и F20 runtime сохранены отдельными commits95494c3/68c7d65.
Следующие F23/docs/CI commits смотреть через `git log`; этот файл записывается до final push.
Actual final CI смотреть на опубликованном HEAD и в ignored `.tools/f23-final-ci.json`
(будет создан после завершения GitHub run). Исторический4059e45 CI не заменяет final SHA.

Full ещё НЕ завершён: host encryption/OS evidence, operational ≤24h backup schedule
и7daily/4weekly retention, requirement-specific ASVS253 review/owner N/A открыты.
Host encryption всё ещё неизвестно; пользователю предложен admin terminal
`manage-bde -status C:`. В UI Windows не заходили: computer-use guidance запрещает
автоматизацию security apps. Ни настройки ОС, ни ключи/защиту хоста не меняли.
Новых Jira POST0; unknown original r1 операции не повторялись и сохраняются.

Детальная хронология ниже историческая; pending scan/build/rollback пункты ниже уже superseded.

## Новое продолжение 16 ноября — читать первым

- HEAD `68c7d65`: Jira runtime, вся исходная dirty F20 работа, failed/unknown reports
  и новая полная регрессия сохранены коммитом. `95494c3` отдельно сохраняет F22 owner review.
  Эти два коммита пока НЕ pushed. Остальные F23/docs/CI изменения остаются dirty; не discard.
- F20 r3/subnet66: **603 passed, 71 skipped, 0 failed**,675.94s,
  `docs/full/evidence/f20/backend-regression-20261116T063232858.xml`.
  Jira native8, F21 process4, readiness7 выполнены без skips/failures.
  API readiness допускал только0020/0021; исправлен для0022/0023.
  В reused r1 были admission failures; fresh r2 дал602/1/71 с diagnostics timeout.
  Отдельный observability5/5 и полный fresh r3 прошли. Все failed XML сохранены.
- Backend runner теперь поднимает/проверяет API dependencies, использует backend admission
  limits, maxfail3, faulthandler60s и уникальные отчёты/каталоги. r1 с live receipts не очищался.
  Явный `refresh-full-f20-manager.py` обновляет токены без перезаписи ACL и без Jira calls.
  r1/r2/r3 остановлены с сохранением volumes. За продолжение **новых Jira POST0**.
- Изоляция MVP несколько раз прошла с полным `git rev-parse bec833b`; short SHA как аргумент
  gate не подходит. Source/.env/images/volume fingerprints совпали. Main Full не мигрировался.
- Fresh `app:f20`, `tests:f20`, `web:f20` собраны. F23 generator сверил183 Python-файла
  и web/dist с baked images и закрепил8 immutable image IDs.
- F23 pilot1/subnet70 остановлен после ошибки топологии: internal-only Docker network не
  публикует loopback ports. Данные/ключи сохранены. Pilot2 использует internal73 + edge74
  только web/IdP + management75 только manager. Optional MANAGEMENT_SUBNET добавлен в F17
  setup helper, defaultNone сохраняет старое поведение.
- Pilot2 nativeTLS8/8, browser14/14 и реальная master-realm admin MFA7 checks прошли.
  Первый admin enrollment probe ошибочно декодировал raw hidden totpSecret как Base32;
  незавершённая попытка сохранена в private admin-mfa, ключ зарегистрированного фактора
  не сбрасывался. Исправленный probe прошёл, затем обычный browser14/14 прошёл с adminOTP.
- Whole-pilot encrypted backup:59 tables,5 named-volume archives (IdP, manager data/audit,
  telemetry journal/seal), private config; encrypted6,034,124 bytes. Key separate directory:
  `.tools/f23-pilot-recovery-keys/opspilot-full-test-f23-pilot2/backup.key`.
  Archive `.tools/f23-pilot-backups/opspilot-full-test-f23-pilot2/pilot.enc`; не печатать/терять ключ.
  Pilot2 остановлен. Backup включает actual admin MFA; plaintext DB dumps на host не писались.
- Recovery1/subnet76 остановлен: pg_restore отклонил уже созданные init.sql schemas.
  Recovery2/subnet79 остановлен:59 table match + pending approval прошли, затем browser
  probe ошибочно предположил actions-array вместо singular v1 action. Оба failed reports
  сохранены в `docs/full/evidence/f23/local-pilot-20261116/restore-attempt*.json`.
- **Recovery3/subnet82–84: whole cold restore65.77s**, offline comparison15.62s,
  59 table hashes matched before writes; пустая DB, NOLOGIN/readonly до сверки,
  manager unseal/token refresh, IdP, all services, fresh browser MFA/approval и adminMFA.
  Committed replay extra tickets0; pending new ticket1. Images preloaded; это не host rebuild SLA.
  Recovery3 сейчас running; edge8443/8543, manager18270. Main/MVP не переключались.
  Actual recovered manager rotation/revoke/seal/CAS rollback8 checks passed. Это signature
  overlap/config rollback, не новая in-flight business-job или deployment-image rollback приёмка.
- Публичные curated proofs: `docs/full/evidence/f23/local-pilot-20261116`.
  New scripts: `test-full-f23-local-pilot.ps1`, `prepare-full-f23-local-pilot.py`,
  `rehearse-full-f23-pilot-recovery.py`, `security_pilot_admin_mfa.mjs`,
  `security_pilot_restore_browser.mjs`, `check-full-f23-pilot-manager.py`, image scan runner.
- **Текущий незаконченный scan:** `scan-full-f23-pilot-images.ps1`, attempt r1,
  exec session47161. Fresh Trivy digest790fd66... uses consistent DB; raw reports
  `docs/full/evidence/f23/local-pilot-20261116/images-r1`, ignored archives/log
  `.tools/f23-scans/opspilot-full-test-f23-recovery3-r1`.
  App0 H/C, Redis0; web3 HIGH libxslt1.1.43-r3→r4; PostgreSQL19 HIGH
  krb5-libs1.22.2-r1→1.22.3-r0 иlibxslt r3→r4. OIDC/manager scan ещё ожидались.
  `web/Dockerfile` и postgres stage `infra/full/Dockerfile` уже имеют minimum patch
  constraints, но новые `web:f23`/`postgres:f23` ещё НЕ собраны. Старые tags/volumes не менять.
  После всех findings собрать отдельные patched images, проверить raw scans и новый logical
  restore; не подключать сохранённый physical PG volume к новому libc.
  Restore runner поддерживает `--image-overrides path.json` (allowed runtime keys→sha256).
- Artifact secret checks: initially73 candidate files +6 F20 log streams, matches0/JWT0;
  последующая проверка76 candidate files включая pilot secrets тоже0.253 ASVS rows unchanged.
  Final scan после новых F23 файлов/backup keys ещё нужен. Defender enabled/signatures15Nov;
  это НЕ OS vulnerability scan.
- Пользователь дважды прислал отказ Get-BitLockerVolume (первый раз была опечатка).
  Предложено запустить **Terminal от имени администратора**, `manage-bde -status C:`.
  Ответа с фактическим статусом пока нет. Шифрование host неизвестно; ОС не меняли.
- Всё ещё открыто: patched exact-image gates, final CI SHA, storage/OS evidence,
  production backup schedule7daily/4weekly, deployment-image rollback, requirement-specific
  release review253. Не объявлять F23/F24/L2 done.
- F22 CI shell теперь включает Jira boundary8 и readiness/transport/verification tests.
  Workflow push paths удалены, чтобы CI запускался на каждом SHA Full branch, включая final docs.
  После scoped commits/push нужен actual CI final SHA; historical4059e45 CI не заменяет его.

Ниже сохранён исходный handoff15 ноября; новые результаты выше имеют приоритет.

Рабочая папка `C:/Users/user/Desktop/code/Ops`, ветка `codex/opspilot-full`.
Проект НЕ завершён. Это сводка последних наблюдений 15 ноября; сначала проверьте фактическое состояние.
Читайте также AGENTS.md, START-HERE.md, спецификацию и canonical tracker. Их старые запреты и статусы частично устарели; новые разрешения ниже получены в текущем чате.

## Разрешения владельца

- Закончить Full и все проверки, включая разрешённую тестовую Jira KAN.
- Коммит и push разрешены. GitHub доступен.
- Целевая среда F23: локальный TLS-пилот на этом компьютере.
- Владелец принял весь предоставленный человеческий пакет F22 словами «я всё принял». Это не приёмка ASVS или всего проекта.
- Платные LLM-вызовы запрещены. Использовать scripted. MVP и основную Full БД сохранить.
- Не запускать агентов без явного разрешения. Лабы запускать последовательно.

## Git и CI

Последний известный HEAD/pushed: `4059e45` (patch OpenTelemetry 1.45.1 → 1.45.2).
Успешный удалённый CI: https://github.com/shibumi2906/opspilot/actions/runs/43725330142
На этом SHA: Full scripted 50/50, MVP 12/12, security gate passed.
Артефакты скачаны в `.tools/f22-ci-43725330142` (ignored).
Это НЕ CI новых незакоммиченных изменений Jira. После исправлений нужен CI final SHA.
Старый F09 workflow переведён в ручной исторический запуск; F22 push trigger расширен на source/tests/migrations/dependency files.

## Незакоммиченные изменения

Обширный runtime Jira: contracts, registry, native HTTPS transport, manager credentials, shared authorization, signed grants, plans, independent verification, API reconciliation, UI approval/reconciliation.
Миграции: `0022_jira_operations`, `0023_jira_audit`. Новая тестовая БД уже прошла обе.
Нельзя discard рабочее дерево. Owner review F22 также пока не закоммичен.

Основные файлы: `src/opspilot/mcp_server/services/jira.py`, `integrations/jira_transport.py`, `integrations/jira_registry.py`, `api/routes_jira.py`, `runtime/plans.py`, `mcp_client/client.py`, `mcp_server/services/tickets.py`.
Runner: `scripts/test-full-f20.ps1`, override `compose.full.f20-checks.yaml`.

## Что реально проверено

- 315 unit tests passed; `docs/full/evidence/f20/runtime-units.xml`.
- 8 native MCP/PostgreSQL boundary tests passed; `runtime-boundaries-final.xml` и ignored log `.tools/f20/opspilot-full-test-f20-r1/runtime-boundaries-final-r2.log`.
  Контролируемый vendor stub; настоящие API decisions, grants, fencing, RLS, receipts и audit. Потеря ответа, отказ/rate limit, ошибка GET после POST, mismatch, late duplicate, slow response 6s, replay/tampering.
- Mypy: 159 source files passed. UI TypeScript/Vite build passed.
- Реальные issue и отдельный comment созданы в KAN и независимо проверены.
- `docs/full/evidence/f20/live-existing-replay.json`: comment replay вернул saved receipt, issue replay отказал после expiry; повторная полная сверка маркеров показала 0 дублей, 0 новых POST.
- Исправления Jira: comment marker должен быть JSON object; правильный property URL `/rest/api/3/comment/{id}/properties/...`. Ранее HTTP400. Полученный provider ID теперь сохраняется ДО дополнительных GET. MCP Jira deadline 45s, обычные tools 5s. Reconciliation имеет общий deadline40s и ищет поздние дубли даже после verified.

## Неудачные попытки нельзя скрывать или повторять

Ранее несколько comment attempts получили unknown; HTTP400 удалось доказать для отдельной диагностической попытки. Старые unknown не переотправлялись. Отсутствие объекта не разрешает новый POST.
Live scripts используют уникальные attempt labels и exclusive report creation. Не удалять отчёт, чтобы повторить live script.
Публичные failed attempt reports лежат рядом с успешными. Сохранять честные denominators.
Реальные run IDs:
- `dd4a28db-4269-4c6c-99c4-263eb0fb1cf0`: issue verified, comment unknown.
- `894690a0-f3c1-4b8f-bc04-d68304a68100`: первый real issue action.
- `b008b2b4-ab9a-406e-9e8f-a759d90a0955`: первый unknown comment action.
- `a4db3812-c72f-439a-9527-ea60e58c1eab`: успешный standalone real comment.
Не печатать внешние IDs и credentials: в evidence используются hashes.

## Текущий незаконченный backend regression

Полный backend запуск был неправильно подготовлен: API service не был поднят.
Запуск остановлен SIGINT после 464.84s: 401 passed, 16 failed, 40 skipped; это НЕ успешная регрессия.
Лог `.tools/f20/opspilot-full-test-f20-r1/rehearsal.log`; XML `backend-regression.xml`.
Большая часть failures — API-dependent. Причина двух failures action_grants и двух F21 ещё не разобрана; не списывать их автоматически на setup.
Последний шаг поднимал `api collector` в F20 lab; результат ещё не дочитан.
Ignored log: `.tools/f20/opspilot-full-test-f20-r1/api-start.log`.
Нужно подготовить корректные сервисы, разобрать failures, выполнить regression заново с bounded diagnostics. Уточнить script Backend preflight/startup.

## Изолированный F20 lab

Project `opspilot-full-test-f20-r1`, subnet `10.245.64.0/24`, manager project suffix `-manager`, port18240.
Private state `.tools/f20/opspilot-full-test-f20-r1`.
Manager tokens истекают через час; после ночи их надо явно обновить, сохраняя ключи.
Повторный bootstrap setup-full-f17-manager.py сохраняет manager grant keys, но переписывает ACL f17-mcp: затем восстановить exact Jira credential ACL через setup-full-f20-jira.py.
Credential `.tools/f20-private/credential.json`, raw token `.tools/f20-private/jira-token.txt`. Не показывать содержимое.
Enrollment script `scripts/setup-full-f20-jira.py`.
Site makegrigorev.atlassian.net, KAN project10001, Task10006, connector UUID(int2020), demo tenant, GreenShop customer UUID(int1).

Основная Full БД остаётся0019. MVP отдельный checkout; последний isolation prebuild прошёл.
Новые отдельные images `opspilot-full/app:f20` и `tests:f20` собраны с patched dependencies; не считать их окончательными: source менялся после начала build. Перед pilot rebuild и exact source matching.
Dockerfile теперь имеет Full-specific UV cache scope и bounded download settings после зависшего build. Старая попытка была остановлена только для собственного docker build process.

## F23/F24 — ещё не завершено

Исторические F23 TLS/MFA и backup/restore/worker checks остаются scoped evidence; 22.86s НЕ полный RTO.
Новый `scripts/prepare-full-f23-local-pilot.py` только написан, НЕ запущен/проверен. Есть lint E501 в embedded image fingerprint code. Должен проверять source matching, pin images, fresh subnet70, отдельный manager, worker без private grant file mounts, non-root web и scripted/no Jira enrollment.
Нужен свежий `web:f20`, полный TLS pilot, реальная admin MFA (старый browser probe прямо оставляет её deployment obligation), manager rotation/revoke, encrypted retention/backup, пустая recovery DB с egress disabled, полный RTO, rollback и final image scans.
Проверка BitLocker `manage-bde -status C:` не получила права администратора; состояние encryption неизвестно. ОС не меняли.
Все253 ASVS protected identities/owners/baseline/N/A поля сохранены. Requirement-specific full release review не закрыт. Не объявлять L2/F24 done по проценту тестов или blanket F22 acceptance.
Обновить README/tracker/START-HERE/AGENTS с фактическим состоянием, сохранить отдельные evidence, выполнить secret/artifact checks, commit/push и CI final SHA.

## Остановка инструментов

Последняя require_escalated команда (чтение Docker logs и файлов) НЕ была выполнена: auto-review не смог завершиться из-за лимита использования аккаунта, а не из-за небезопасности действия. Не обходить approval review. После восстановления доступности продолжать обычным способом.
На момент остановки labs могли оставаться запущенными. Сначала проверить их состояние; не трогать чужие контейнеры/volumes и не очищать Docker глобально.
