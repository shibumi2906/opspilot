# F09 — action revisions / approval TTL / execution grants

Профиль: local Full, scripted synthetic fixtures; целевой стандарт OWASP ASVS 5.0.0 L2.
Parent source: f4d84e2. Реализация и evidence фиксируются одним F09 commit;
точный tested tree manifest будет сохранён отдельно. Полный ASVS L2: NOT_MET.

## Реализация

Migration 0011 отделяет logical intent от immutable revisions, снимает single-action/run
uniqueness, добавляет approval version/DB expiry и grant registry. Старые завершённые
receipts сохраняются; legacy approved/unexecuted отзываются, новое согласие обязательно.
Core выдаёт отдельный purpose-bound Ed25519 grant ≤60 секунд и остатка approval TTL.
MCP независимо проверяет binding, актуальные права/approval/revision/fence и потребляет
grant в одной транзакции с ticket+receipt. API получает только service-context private
keys, worker — grant issuer keys, MCP — public ring. JWT остаётся в transient header.
Human edit supersedes старое согласие; stale/opposite decision 409, expiry 410.
Функциональная область остаётся create_ticket; F10 tools и F11 DAG не введены.

Контракты и ограничения: [security design](../../f09-security-contracts.md).
Requirement-specific contributions: [ASVS backlog](../../../security/asvs-l2-requirement-backlog.json);
локальное подтверждение текущих изменений не является независимым L2 acceptance.

## Воспроизводимые проверки

- `scripts/test-full-f09.ps1`: build, fresh DB/migrate/seed/identity, Ruff/format/mypy,
  Python integration/contracts/unit, browser, two-worker process recovery/fences,
  pinned image scanner + Python/npm audit, 12 scripted evals.
- `scripts/test-f09-upgrade.ps1`: изолированная БД 0010, pinned pre-F09 synthetic fixture,
  unexecuted legacy approval, upgrade HEAD, canonical backfill + сохранение двух receipts.
  Для повторения использовать новый project, без удаления старых volumes.
- `scripts/test-security-local.ps1 -SkipBuild -ReportDir docs/full/evidence/f09/tls`:
  настоящий local TLS/IdP MFA/BFF/MCP/DB, synthetic credentials, verified effect.
- `scripts/check-full-isolation.ps1 -MvpPath <MVP> -ReportPath docs/full/evidence/f09/mvp-after.json`.

## Ход проверки

Первый финальный кандидат: Ruff/format/mypy проходят; 300 Python tests passed / 9 skipped,
12 browser tests passed, queue process recovery 5 passed. Обнаруженные ранее ошибки
cancellation-before-dispatch, missing-approval row lock и legacy mutation assertion исправлены;
они вошли в полный passing набор. Это не замена проверки исправленного runtime ниже.

Первоначальный Debian runtime scan обнаружил 61 HIGH / 3 CRITICAL findings (включая uv0.13.1).
Web runtime scan — 5 HIGH. Исходные findings сохранены; gate не обходился.
Remediation: поддерживаемый digest-pinned Python Alpine runtime, uv0.13.4 и vendor security
updates для app/web. После изменения runtime повторяются все необходимые gates.
Окончательные результаты приведены ниже.

Production deployment, managed secrets, operational controls и remote CI в этом этапе
не запускались. Платных provider calls, внешних connector writes и push нет.



Неуспешные кандидаты не скрыты: первый process-fence fixture ожидал отказ только в MCP,
хотя F09 уже отклонял stale Core issuance (SQLSTATE 40001); fixture скорректирован на этот
конкретный запрет. В параллельном повторе один recovery child закрыл stdout без stderr;
точная причина не подтверждена, в fixture добавлена exit-code диагностика. Заключительная
приёмка выполняется последовательно без TLS lab и фоновых build-процессов.
TLS browser navigation race при tenant selection устранён ожиданием main-frame navigation,
не увеличением/отключением security deadlines. Отдельный regression покрывает expiry новой
revision после уже завершённого resume старой: повторная постановка durable resume обязательна.
Начальные scan findings: app-image-before-remediation.json; окончательные scans — security/.


Промежуточная последовательная приёмка до удаления pip: Python 301 passed / 9 skipped (258.76 s),
Ruff/format и mypy (111 source files) проходят. Live DB проверила 170 новых security events
с allowlisted payload и раздельными DB privileges. Live key separation проверена отдельно
и внесена в release script: [key separation](key-separation.json).
Fresh TLS/MFA lab после навигационного исправления: 8 TLS probes + 11 browser/security checks,
включая отдельного approver, проверенный ticket, disable/re-enable session revocation.

Browser regression: 12 passed (1.7 m). Dedicated durable queue process gate: 5 passed
(71.12 s). Dedicated fencing gate: 3 passed (51.93 s), kill/stop/partition;
[process reports](process/) фиксируют один итоговый effect и запреты stale worker.


## Окончательный результат

Все обязательные local F09 gates пройдены на конечном runtime без системного pip:
[checks.json](checks.json), [полный release log](checks.log), [TLS log](tls-checks.log).
Python 301 passed / 9 skipped (263.21 s), браузер 12 passed (2.5 m), queue process 5 passed,
fencing 3 passed. Ruff/format/mypy: pass. Scripted evals 12/12, hard safety gate true,
0 unauthorized writes / duplicates / false verified success; [measured report](evals/scripted.md).

[SCA app](security/app-image.json) и [SCA web](security/web-image.json): 0 findings;
[Python audit](security/python-audit.json): 89 distributions, 0 known vulnerabilities;
[npm audit](security/npm-audit.json): 0. Последний candidate с pip26.2.2 отклонён из-за
уязвимых vendored libraries; его отчёт сохранён отдельно (app-image-pip-vendor-candidate.json).
Неиспользуемый системный pip удалён из конечного image; uv0.13.4 и app dependencies сохранены.
Проверка [system trust store](security/trust-store.json) также проходит.

Конечный TLS/MFA lab: 8 TLS probes + 11 security/browser checks, verified create_ticket
от отдельного approver. [Upgrade](upgrade-release.log): 2 committed receipts/tickets сохранены,
3 revisions backfilled, legacy unexecuted approval revoked. [Source/image manifest](source-tree.json)
связывает проверенный dirty snapshot parent f4d84e2 с содержимым финального локального коммита;
eval commit — parent SHA с явным dirty_snapshot=true, не утверждение о тесте чистого parent.
Remote CI/real provider/production L2 не заявляются пройденными. F10 не выполнялся.


Обычный Full восстановлен на migration0011: [readiness/UI smoke](restored-full.json),
оба worker healthy. [MVP after fingerprint](mvp-after.json) совпадает с before: 184 files
включая env, main/head, image tags, volume metadata и read-only content. Тестовые контейнеры
и сети убраны; volumes/images сохранены: [cleanup](test-resource-cleanup.json).
