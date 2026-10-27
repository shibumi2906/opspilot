# Проверка F01–F08 по OWASP ASVS 5.0.0, целевой L2

Дата: 27 октября 2026. Проверенный Full commit: `fe78a5c17d8e88c4c0f58001366855c589adf518`.
Worktree: `C:\Users\user\.codex\worktrees\opspilot-full-f01\AI Incident & Operations Agent`.

**Вывод: текущий срез F01–F08 не достигает ASVS L2.** Положительные controls уже есть,
особенно tenant/object authorization, server-side CSRF, scoped MCP tokens, atomic workflow
commands и immutable run audit. Однако конкретные gaps и неполнота проверки не позволяют
заявить соответствие L2. Функциональный статус done у F01–F08 не означает ASVS acceptance.

Основа — [официальный stable ASVS 5.0.0 release](https://github.com/OWASP/ASVS/releases/tag/v5.0.0_release),
а не изменяемый master/bleeding edge. Учтены все 70 L1 и 183 L2 requirements, всего **253**.
Полная ID-матрица: [matrix.json](matrix.json). Version/tag/commit, download SHA-256,
атрибуция OWASP и fingerprints reviewed source: [sources.json](sources.json).
Идентификаторы далее имеют префикс `v5.0.0-`; требования L3 не использовались как обязательные L2.

## Граница доказательств

Проведены source/config review, сверка сохранённых F01–F08 evidence и in-memory probes
конкретной cookie-функции/DTO. Пробы и версии host dependencies: [local-probes.json](local-probes.json).
Host Pydantic/FastAPI отличаются от pinned container dependencies; эти пробы характеризуют
исходный код, но не заменяют проверку развёрнутого приложения.

Docker daemon сейчас недоступен: отсутствует `dockerDesktopLinuxEngine`. Поэтому свежие
HTTP/JWKS/IdP/TLS/browser/DB security tests не выполнены. Предыдущие 239 backend passes,
12 browser cases и fault/eval results являются историческим stage evidence, а не новыми
ASVS-тестами. Не проводились brute-force/load, SCA/CVE/image scan, проверка backup/at-rest
или аудит production deployment. Условия и ограничения: [verification.json](verification.json).
Приложение, IdP accounts/memberships, MVP и функциональные trackers не менялись.

| Статус | Количество | Значение |
| --- | ---: | --- |
| supported | 73 | Scoped control подкреплён кодом и/или recorded evidence; это не независимый ASVS pass |
| partial | 42 | Есть реализация, но control или доказательство покрыты не полностью |
| gap | 39 | Найден конкретный пробел относительно L2 target, включая будущий production profile |
| not_verified | 47 | Requirement-specific доказательств недостаточно |
| not_applicable | 52 | Условная функция отсутствует в F01–F08; applicability требует подтверждения владельцем |

Эти числа не являются процентом compliance и не означают «39 уязвимостей»: один finding
может затрагивать несколько requirements. Отсутствующая обязательная MFA не помечена N/A.
IdP controls остаются в assurance boundary: делегирование Keycloak не доказывает их выполнение.
Условно исключены, например, file upload, GraphQL, WebSocket, WebRTC, SAML и OTP/PSTN flows.
Если функции появятся, их applicability необходимо пересмотреть.

## Приоритетные findings

P1 ниже — приоритет закрытия перед заявлением L2/пилотом, а не присвоенный CVSS и не
утверждение, что обнаружен эксплуатируемый internet-facing endpoint. Текущий профиль
явно локальный и синтетический; его ограничения отделены от дефектов реализованного кода.

### ASVS-01 — transport security отсутствует в текущем профиле · P1

Requirements: `v5.0.0-3.4.1`, `12.2.1`, `12.3.1`, `12.3.3`; часть certificate/cipher
requirements остаётся not_verified, а не объявлена небезопасной по предположению.

`compose.full.yaml:14–23` задаёт HTTP origin, issuer и OTLP; `web/nginx.conf:2` слушает 80,
proxy использует HTTP. `infra/identity/opspilot-realm.json:4` содержит sslRequired=none.
MCP, IdP и telemetry links не имеют production TLS profile. Для DB нет доказательства
verify-full TLS. HTTPS OpenAI endpoint не защищает остальные связи. Loopback/Docker network
уменьшают exposure, но не выполняют эти L2 requirements.

Закрытие: production TLS 1.2/1.3 и certificate validation, internal transport protection,
DB SSL verification, корректная plaintext-rejection policy для API и HSTS для HTTPS browser
hosts (минимум год и includeSubDomains для L2). Нужны handshake/certificate negative tests.
Owner: F23 плюс явно добавленный internal-transport security gate; одного внешнего reverse
proxy недостаточно. Actual ciphers, certificate trust и IdP RSA modulus сейчас не измерены.

### ASVS-02 — cookies не изолированы hostname и не имеют требуемых prefixes · P1

Requirements: `v5.0.0-3.3.1`, `3.3.3`, `3.5.4`.

`src/opspilot/auth/http.py:81–90`: имя `opspilot_session`, path=/, HttpOnly, SameSite=Lax,
Secure зависит от app_origin. Host probe подтвердил Secure=false для HTTP; на HTTPS Secure
становится true, но __Host-/__Secure- prefix всё равно отсутствует.

В default локальном профиле Full UI, MVP UI и IdP используют 127.0.0.1 с разными портами. Cookies разделяются по host/path,
а не по порту: это свойство протокола, а не доказанный incident с утечкой в данном окружении.
Раздельные Docker projects/volumes/порты не дают browser-cookie isolation.
См. [RFC 6265 §8.5](https://datatracker.ietf.org/doc/html/rfc6265#section-8.5).

Закрытие: разные hostnames для независимых приложений/IdP, HTTPS, __Host- session/binding
cookie с Secure+HttpOnly+Path=/ без Domain и безопасная миграция/удаление старых cookies.
Проверить cookie sending/overwriting между hosts в браузере. Owner: F03 hardening + F23.

### ASVS-03 — browser headers неполны, nginx inheritance скрывает часть существующих · P1

Requirements: `v5.0.0-3.4.3`, `3.4.4`, `3.4.5`, `3.4.6`.

CSP и frame-ancestors отсутствуют. `web/nginx.conf:5–6` задаёт nosniff/Referrer-Policy на
server level, но locations имеют собственный add_header Cache-Control на строках 11/17/21.
По [правилам nginx](https://nginx.org/en/docs/http/ngx_http_headers_module.html#add_header)
такой location не наследует parent add_header при стандартном режиме. Это статический
config finding, fresh HTTP confirmation сейчас недоступен. Direct API также не добавляет
этот набор headers (`src/opspilot/api/main.py:38–56`).

Закрытие: единый header policy для UI/API и всех response statuses, CSP с trusted source
policy, object-src/base-uri protection и frame-ancestors; устранить inheritance gap.
Проверить 200/redirect/401/403/404/500 через nginx и direct API. L2 не требует применять
L3 per-response nonce policy как единственно допустимый вариант.

### ASVS-04 — L2 authentication strength/IdP policy не обеспечены · P1

Requirements: `v5.0.0-6.3.3`, `6.8.4`; password/recovery/IdP behavioral requirements
в значительной части not_verified.

Realm импортирует synthetic users с password credentials и temporary=false. MFA policy
или документированного L2 exception/compensating controls не найдено. Recorded browser
flows подтверждают password login. `src/opspilot/auth/oidc.py:42–64` проверяет подпись,
issuer/audience/nonce, но не acr/amr/auth_time и не production authentication-strength contract.
Один общий generated demo password не является committed/default root/root secret,
однако такой fixture profile нельзя переносить в production без отдельной политики.

Закрытие: MFA/допустимое стандартом documented exception, strength/freshness contract,
IdP password/anti-bruteforce/recovery policy и негативные тесты. Hardware/phishing-resistant
factor не объявляется здесь обязательным требованием L2. Owner: отдельное F03 security
hardening + F23 acceptance; исходная последовательность F09–F24 сама по себе MFA не обещает.

### ASVS-05 — session lifecycle ограничен absolute TTL и текущим logout · P1

Requirements: `v5.0.0-7.1.1`, `7.1.2`, `7.3.1`, `7.4.2`, `7.4.5`, `7.5.2`, `7.6.1`.

`src/opspilot/auth/store.py:36–69` проверяет revoked_at/expires_at и заново загружает
memberships. Это хороший серверный контроль, но в `ServerSession`
(`src/opspilot/db/models_identity.py:38`) нет idle/last-seen механизма. TTL по умолчанию
8h (`src/opspilot/config.py:37`) не является сам по себе нарушением: отсутствуют idle
policy, risk justification и reauthentication coordination.

Нет BFF session inventory/revoke-all для пользователя/администратора и связи IdP account
disable/deletion/password reset с текущими BFF opaque sessions. При отзыве memberships
новые действия блокируются; это не тождественно обязательному завершению сессий при
отключении учётной записи. IdP-wide logout прямо не обещан в docs/full/identity.md.

Закрытие: документировать idle/absolute/concurrent limits, реализовать server-side idle
expiry, recent-auth policy и координацию IdP→BFF termination. Проверить disable/reset,
параллельные сессии, revoke-all и невозможность восстановить сессию старым token.
Owner: F03 hardening; эти acceptance tests следует добавить явно, не считать покрытыми F09.

### ASVS-06 — приватный snapshot остаётся в DOM после потери сессии · P1

Requirement: `v5.0.0-14.3.1`.

AuthGate получает identity один раз (`web/src/AuthGate.tsx:25–35`). В
`web/src/hooks/useRun.ts:81–91` ошибка запроса обновляет error, но не очищает snapshot.
После 401/expiry/revocation ранее загруженные evidence/report продолжают жить в React state
и отображаться в DOM. Успешный logout очищает sessionStorage и reload, но это лишь один путь.
Сервер продолжает защищать новые запросы — findings не утверждает обход backend authorization.

Закрытие: общий auth-expired/forbidden handler, clearing приватного UI state/DOM и csrf
state; локальная очистка logout должна работать и при offline, отдельно от подтверждения
серверного revoke. Проверить 401 после открытого run, expiry, role removal, tenant switch,
offline logout и navigation/back behavior. Owner: исправление в текущем UI/F14 hardening.

### ASVS-07 — нет aggregate anti-automation/admission controls · P1

Requirements: `v5.0.0-2.4.1`, `6.3.1`, `15.1.3`, `15.2.2`.

Per-run budget и два worker ограничивают одну обработку, но не число создаваемых runs,
объём очереди или login attempts per actor/tenant/global. `/auth/login` вызывает new_login,
который пишет login_attempts; throttling на BFF/nginx не найден. Effective IdP brute-force
policy не подтверждена. Pydantic ограничивает длину уже распарсенного request, что не заменяет
API request-body admission limit. Нагрузочная эксплуатация в этом аудите не выполнялась.

Закрытие: user/tenant/global request и queued-job quotas, login anti-automation, bounded
body/header sizes до parse, concurrency/timeout/backpressure policy и negative/load tests.
Owner: F15 + отдельное IdP hardening, нагрузочные доказательства F21. Политика должна учитывать
ошибочный lockout невиновного пользователя и корректный trusted-proxy/IP contract.

### ASVS-08 — F07 audit не покрывает полный security-event lifecycle · P1

Requirements: `v5.0.0-16.1.1`, `16.3.1–16.3.4`, `16.4.2`, `16.4.3`.

F07 transactional run events/audit/outbox, actor/epoch metadata, bounded fields и запрет
runtime update/delete — сильная база. Однако `src/opspilot/api/errors.py:40–42` и deny paths
в `auth/http.py`/`mcp_server/auth.py` возвращают denial без security audit event. Нет полного
учёта authz denial, invalid-session/service-context attempts и generic security failures.
Login/logout events существуют, поэтому статус authentication logging — partial, а не «логов нет».

Нет полного all-layer log inventory/retention/access policy и защищённого логически отдельного
security-log sink. OTLP trace allowlist полезен для redaction, но HTTP traces не заменяют
security audit и secure transport. DB append-only ограничения не означают защиту от
privileged administrator tampering или наличие независимого хранения.

Закрытие: структурированные события auth/authz/bypass/error без токенов/credentials,
корреляция actor/tenant/run/reason, secure external sink, access/retention/clock policy и
проверка denial/rotation/collector failure. Owner: F07 hardening, F16/F17/F23.

### ASVS-09 — secrets/data protection lifecycle недостаточен для L2 · P1

Requirements: `v5.0.0-13.3.1`, `13.3.2`, `14.1.1`, `14.1.2`, `14.2.4`, `11.1.1–11.1.2`.

Independent ignored secrets, non-owner DB roles, core-only private signing keys, public-only
MCP mounts и current/next/retire CLI уже реализованы. Это не означает managed production
vault/KMS lifecycle. `.env`/PEM mounts не доказывают создание/доступ/rotation/destruction
в secrets-management системе. В local PEM используется NoEncryption с chmod 0600;
эффективные host ACL/backup protections сейчас не проверены. Утечка секрета не обнаруживалась.

Нет полного data classification/protection policy для prompts, evidence, checkpoints,
events, logs, backups и external provider context. Требования at-rest encryption/retention
должны следовать этой классификации; наличие Docker volume не является encryption evidence.
`store:false` и fixed HTTPS provider URL полезны, но не заменяют data-sharing/minimization policy.
Actual IdP RSA strength не измерена: нельзя объявлять ни RSA-2048, ни соответствие минимуму
ASVS на основании предположения о defaults.

Закрытие: inventory/policy всех key types и данных, vault/KMS/secrets RBAC, rotation/revoke/
destruction drills, защита storage/backups и formal outbound data policy. Owner: F17/F23 и
явный crypto/data protection gate; current/next local signer не закрывает весь lifecycle.

### ASVS-10 — production/dependency assurance отсутствует · P2

Requirements: `v5.0.0-13.4.2`, `13.4.5`, `15.1.1`, `15.1.2`, `15.2.1`, `15.2.3`.

Текущий APP_ENV допускает local/test, IdP запускается start-dev. FastAPI default docs/OpenAPI
включены (`api/main.py:38`), а `/docs` и `/openapi.json` не входят в protected paths
(`auth/http.py:50`). Monitoring имеет отдельный loopback listener. Это не утверждение,
что endpoint доступен из интернета: production exposure policy ещё отсутствует.

Lockfiles и image digests дают воспроизводимость, но не подтверждают отсутствие CVE или
выполнение remediation SLA. В CI нет явного SCA/SBOM/security patch gate; текущая конфигурация
указывает F07 entry point. При этом backend discovery всё равно включает новые F08 tests —
неверно было бы утверждать, что F08 вообще не тестируется. Remote CI в stage evidence не заявлен.

Закрытие: отдельный production profile без synthetic bootstrap, explicit docs/monitoring
exposure decision, SBOM включая OS/container dependencies, актуальный SCA и patch SLA,
security-gate/report traceability. Owner: F17/F23 и security CI. Конкретные уязвимые версии
в этом аудите не устанавливались.

### ASVS-11 — strict typing нуждается в отдельной проверке · P2, validation observation

Requirement: `v5.0.0-15.3.5`, дополнительно `2.2.1`.

`StrictModel` запрещает extra fields, но не включает strict types;
`contracts/api.py:21` объявляет expected_version как обычный int с range constraint.
Host probe принял true как int 1. Это не доказанный authorization bypass и не воспроизведение
на pinned container dependencies: host Pydantic здесь 2.11.7. Matrix status — partial.

Закрытие: проверить pinned runtime, определить canonical type policy, применить strict
int/UUID/boolean handling там, где тип участвует в security/state decision, добавить
negative cases true/1.0/"1" и duplicate-parameter semantics. Owner: validation hardening F08.

## Что уже подтверждено по стадиям

| Этап | Полезная ASVS база | Что это пока не доказывает |
| --- | --- | --- |
| F01 | Раздельные Full/MVP resources, generated secrets, reproducible builds | TLS/production profile, browser hostname isolation, SBOM/CVE assurance |
| F02 | Tenant keys/composite FK/FORCE RLS и non-owner runtime roles | Encryption/secret lifecycle и независимую защиту от компрометации trusted backend |
| F03 | Code+S256, state/binding/nonce, pinned issuer/JWKS, opaque hashed sessions, CSRF | MFA, idle/parallel policy, reauth и IdP→BFF account/session termination |
| F04 | Server roles/owner/tenant checks, public allowlists, scoped signed MCP JWT | Full deny logging, deployed IdP policy и complete production session assurance |
| F05 | Atomic start/resume jobs, отдельный worker, bounded retries/no blind write retry | Aggregate actor/tenant/global admission limits или application-wide DoS устойчивость |
| F06 | Lease/epoch/checkpoint fencing и race/fault evidence | Production availability/load/soak gate и безопасный transport между services |
| F07 | Transactional events/audit/outbox, monotonic replay, runtime append-only controls | Полный security log inventory, все deny/failure events, independent secure sink/retention |
| F08 | Typed allowlisted clarification, version/TTL/replay checks, atomic answer/cancel jobs, truthful effect report | ASVS L2 целиком, strict-type proof на pinned runtime, complete UI auth/DOM lifecycle |

Сильные requirements, например: `v5.0.0-7.2.1–7.2.4`, `8.2.1–8.4.1`,
`9.1.1–9.2.4`, `10.1.1–10.2.1`, `10.5.1–10.5.4`, workflow части `2.3.1/2.3.3/2.3.4`.
Точные conditional exceptions, evidence и ограничения находятся в ID-матрице.
Это не blanket pass остальных функций/будущих endpoints.

## Порядок доведения до L2

1. Зафиксировать production boundary: app/IdP/monitoring hostnames, классификация данных,
   auth strength, idle/absolute/concurrent sessions, egress/secret/log ownership. Выделить
   ASVS hardening gate отдельно от функционального F01–F24 tracker.
2. Закрыть ASVS-01–06: transport/cookies/headers, MFA/IdP policy, server session lifecycle,
   clearing приватного UI. Часть требует дополнения F03, а не ожидания F09 action grants.
3. Закрыть ASVS-07–09: aggregate limits, security audit и managed secrets/data policy.
   F15–F17/F23 уже дают места для этой работы, но их исходные acceptance criteria следует
   сопоставить с конкретными ASVS IDs, включая controls на стороне IdP/infrastructure.
4. Выполнить production/SCA/crypto verification и type hardening. Получить доказательства
   по всем applicable not_verified/partial requirements; назначить и подтвердить N/A.
5. На pinned deployed profile провести authenticated ASVS negative tests, browser header/
   cookie/DOM matrix, IdP MFA/disable/reauth/password/recovery tests, TLS/certificate/JWKS
   checks, quotas/DoS defenses, role/tenant denial logging, secret rotation и retention drills.
   Затем повторить F01–F08 regression с сохранением MVP isolation.

Обязательные свежие проверки после восстановления Docker: HTTP responses/headers через
UI и direct API; actual Set-Cookie; cookie isolation по hosts; /docs/monitoring exposure;
IdP effective config и RSA strength; expiry/disable/reset/revoke-all; private DOM purge.
Отдельно нужны SCA/SBOM и production TLS/storage/backup evidence: они не следуют из
наличия unit/integration tests и не считаются автоматически выполненными.

Итоговая acceptance формулировка: все applicable L1+L2 requirements имеют положительное
requirement-specific verification evidence; N/A согласованы с владельцем; gaps закрыты
или обработаны строго допустимым самим стандартом способом. Текущий отчёт этого результата
не утверждает и не является сертификацией OWASP.
