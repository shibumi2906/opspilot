# ASVS L2: локальный security-контур F01–F08

Область: Full, F01–F08 после `fe78a5c`; OWASP ASVS **5.0.0**, целевой L2.
Выбор пользователя: сначала изолированный локальный security-контур. F09 не реализуется.
Исходный аудит сохранён без пересчёта задним числом: [baseline](../asvs-l2-f01-f08-2026-10-27/README.md).

**Это проверяемый hardening baseline, не утверждение о полном соответствии L2.**
Статусы исходной матрицы нельзя автоматически заменить на pass по наличию нового профиля.
Production deployment, операционные контроли и независимая проверка всех applicable требований
остаются отдельными критериями приёмки.

## Запуск

Из Full worktree: `powershell -File scripts/test-security-local.ps1`.
Для уже собранных образов: добавить `-SkipBuild`. Нужны Docker Desktop и исходный Full `.env`
для сборки базовых образов; credentials security-контура генерируются независимо.
Скрипт прекращает работу при любой неуспешной проверке.

Проект `opspilot-full-security`; собственные `pgdata` и `oidcdata`, собственная сеть.
БД называется `opspilot_full_test`, чтобы сохранить запрет соединений Full с MVP database.
Порты только loopback: приложение `https://app.opspilot.localhost:8443`,
IdP `https://idp.opspilot.localhost:8543`. API/MCP/PostgreSQL не публикуют host ports.
Обычный Full development profile остаётся отдельным и не считается hardened deployment.

Игнорируемый `.tools/security-local/` содержит secrets, fixture credentials, OTP seeds,
TLS leaf keys, CA и отдельный ключ MCP core. Генератор отказывается перезаписывать существующий каталог.
CA не устанавливается в Windows. Срок CA 30 дней, leaf 14 дней; истечение требует
нового лабораторного выпуска и повторной проверки. CA private key не монтируется в runtime API/MCP/worker;
ключ MCP core доступен только доверенным API/worker, MCP получает public key. Используются только синтетические данные.
Не публиковать этот каталог, compose JSON или browser storage state.

Браузерная автоматизация принимает только SPKI двух сгенерированных leaf certificates;
нет глобального `ignoreHTTPSErrors`. Отдельные HTTPX-пробы проверяют CA/hostname обычным
TLS verifier и отрицательные случаи. Node при вызове IdP admin API доверяет только CA lab.
Это лабораторная настройка доверия, не evidence для публичного production PKI.

## Реализованные контроли

* Native TLS API/MCP, HTTPS IdP и ingress, PostgreSQL TLS с `verify-full` и серверным
  запретом network plaintext authentication. Проверка CA и имени на исходящих клиентах.
* Hardened startup запрещает HTTP endpoints, demo self-approval, слабые session settings,
  неограниченные admission caps и PostgreSQL DSN без `verify-full`.
* Обязательный password + TOTP в отдельном Keycloak flow; RSA 4096; brute-force policy;
  PKCE, точные redirect/origin; BFF требует `acr=2` и свежий integer `auth_time`. Это flow пользователей приложения;
  master bootstrap admin в lab — отдельная synthetic administrative fixture, не production MFA policy.
  Лабораторный assurance mapper допустим только вместе с этим mandatory two-factor flow;
  его перенос в иной flow без повторной проверки недопустим.
* Оpaque host-only `__Host-` Secure HttpOnly cookies; серверные absolute/idle deadlines,
  GET polling не продлевает idle; maximum parallel sessions и recent MFA для опасных действий.
* IdP access token сохраняется зашифрованным Fernet; TTL BFF ограничен access-token TTL.
  На каждом authenticated request provider userinfo подтверждает живую IdP-сессию.
  Недоступный provider даёт fail-closed 503; invalid/disabled session отзывается в БД.
* UI/API списка собственных сессий и их отзыва; отзыв всех; tenant-scoped admin disable/revoke.
  Tenant admin не может глобально отключить multi-tenant identity. Worker/domain повторно
  проверяют enabled actor через scope-checked definer function, без SELECT на identity.users.
* CSP, HSTS в HTTPS profile, nosniff, referrer/permissions policy, no-store на успешных
  и ошибочных ответах; TRACE/duplicate security headers/duplicate JSON fields/NaN rejected;
  размер body учитывается и для chunked requests; общий deadline при чтении body.
* Durable atomic actor/login request counters и actor/tenant/global admission caps
  в той же транзакции, что создание run. Превышение возвращает 429; retries idempotent.
* Security denials, неожиданные ошибки, login/logout/session/admin events пишутся без
  payload/token/SQL/exception text; nginx access log не пишет query string; runtime identity role не может удалить security audit.
* Private DOM очищается при 401/403, logout и локальном достижении последнего server deadline,
  включая offline. Offline logout не утверждает, что серверный отзыв состоялся.
* Static bootstrap bearer исключён из hardened MCP: short-lived signed context является
  credential; существующая проверка audience/issuer/key/tenant/action/fence сохраняется.
* `expected_version` принимает strict integer. Обновлён уязвимый certifi в frozen lock.

Проверенные результаты и ограничения прогонов: [tracker](status.md);
связь изменений с требованиями без объявления формального pass: [overlay](verification-overlay.json).

## Что ещё необходимо для L2

| Область | Остаток |
| --- | --- |
| Managed secrets | File source — адаптер для lab, не secrets manager. Нужны выбранный production manager, per-service ACL, rotation/revocation и recovery drill. |
| Logging/monitoring | Structured events и append-only application grants не заменяют отдельный защищённый collector, alerting, retention и проверку tamper/availability. Nginx error diagnostics сохранены; для production нужны защита доступа и redaction чувствительных query-параметров в диагностических сообщениях. |
| Data lifecycle | Нужны утверждённые classification/retention, реализованное удаление/архивация, encryption at rest и восстановление backup. Lab содержит только synthetic data. |
| Identity operations | Проверить MFA административного IdP plane, эффективные password blocklist/recovery/reset/MFA reset, authenticator enrollment/removal notifications и процедуры владельца IdP. Утверждение про все ASVS V6 requirements не делается. |
| Supply chain/runtime | Package SCA — часть проверки; дополнительно нужны image/OS scanning, SBOM, patch SLA и release gate для deploy artifacts. |
| Deployment | Реальные DNS/PKI, ingress exposure, secrets/storage/backup, сетевые ACL и эксплуатационный аудит проверяются на выбранном deployment. |
| ASVS matrix | Все 253 L1+L2 requirements требуют отдельной проверки, обоснования N/A и evidence; прежние supported не равны независимому pass. |

Никакие оставшиеся требования не объявлены N/A лишь потому, что они отсутствуют в F01–F08.
Локальный контур не является сертификацией OWASP.
