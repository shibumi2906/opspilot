# F18: adapter platform и signed observation ingress

Scope: только F18 поверх `017b68bb34e85e95013076d570bd14b5519f842b`.
Schema `0019_adapters`; MCP сохраняет13 canonical tools, graph/state/checkpoint contracts прежние.
Единственный зарегистрированный adapter — **synthetic simulator**. Vendor/staging/live и
production network firewall acceptance остаются F19/F20/F23; Full Pilot и полный ASVS L2 NOT_MET.

## Границы доверия

| Поток | Доверие и контроль |
| --- | --- |
| Admin BFF → config | Session/tenant/admin + существующая recent-MFA policy; CAS version, immutable mapping, FORCE RLS, customer/integration FK и guard; только зарегистрированный origin; body-free audit/cache invalidation |
| MCP → manager | Native TLS и отдельный часовой nonrenewable ACL token; только exact registered `connectors/{tenant}/{connector}/credential`; exact tenant/connector metadata; нет webhook или private grant keys |
| API ingress → manager | Отдельный token только exact registered `connectors/{tenant}/{connector}/webhook`; никакого credential/grant read; routing UUID не становится trusted tenant до HMAC |
| MCP → simulator | Fixed GET `/v1/health`, Bearer + trusted scope IDs; exact HTTPS origin, all-answer DNS verification, pinned IP socket и TLS hostname/CA; никакого redirect/proxy/model URL |
| Producer → public ingress | Raw-body HMAC-SHA256, domain-separated tenant/connector/timestamp prefix, key ID, constant-time compare; DB-clock ±300s, strict typed observation и mapped customer/integration |
| Ingress → PostgreSQL | Отдельная `ops_ingress`, без domain/workflow privileges; receipt и job одной транзакцией **до2xx**; unique tenant/connector/event ID + immutable body hash; replay200, altered event409 |
| Processor → observations | Row-locked `SKIP LOCKED` job, cursor monotonic CAS, observation/receipt/job/audit одной транзакцией; disabled config quarantines pending receipt; нет approval/grant/business write |

`integrations.ingress_config` возвращает только pre-auth mapping/enabled metadata. Для синхронизации
с disable используется отдельная `lock_config`: только текущий trusted tenant, только SELECT
с shared lock. Это не выдаёт UPDATE роли ingress/MCP. PUBLIC execute отозван у этих функций.
Configuration changes serialize с admission; worker locks config на всю обработку. Circuit health
row lock сериализует probe одного connector, failures3 открывают breaker на30s; recovery реальным
успешным TLS probe, без выдачи cached healthy при outage. Events/read cache обходится для любого
configured integration, включая disabled; смена config инвалидирует legacy generation.

## Capability и mapping

| Adapter | Status / observations | Expiration | External write | Idempotency |
| --- | --- | --- | --- | --- |
| simulator, mapping1 | Synthetic health и typed observations | unknown | false | false; local receipt identity обеспечивает ingress replay safety |

Mapping hash детерминирован по version/kind/customer/integration/origin. Изменить mapping существующего
connector нельзя; нужна новая identity. Credential refs вычисляются сервером и не принимают произвольный
manager path. Admin GET не возвращает refs/values. HTTP401 не трактуется как credential expiration.
Webhook status enum не содержит approval; extra fields запрещены. Domain customers/tickets/approvals
не изменяются ни при приёме, ни при обработке события.

## Пределы и отказ

Public Nginx `/ingress/v1/` проксирует raw body без transform, допускает только POST и применяет16KiB/2s body limits; hardened proxy проверяет TLS upstream. Body16KiB, persisted typed payload2KiB, HTTP socket phases0.5s, transport deadline2s/async2.5s;
manager1s/async1.5s. Dedicated executor4 сохраняет permit до реального завершения потока даже после
cancel/timeout; очередь не растёт при зависшем DNS. Ingress slots4 с admission50ms; общий HTTP deadline2s.
Config100/tenant; quota60 новых receipts/min/connector; pending100/connector и1000 globally;
retained10000/connector и100000 globally. При заполнении —429 без удаления replay identities;
повтор уже принятого идентичного события не расходует quota. Массовый lifecycle integration identities
нуждается в отдельном owner-reviewed retention contract; автоматическое удаление не включено.
Хранятся только UUIDs/sequence/status/time/hash/kid, без raw signatures, credential values или free text.

DNS private/loopback/link-local/multicast/reserved/IPv4-mapped ответы запрещены. Local/test simulator
имеет единственное явное исключение: заранее зарегистрированные origin/IP/CA; production его не
принимает. Проверка всех адресов предшествует соединению; второе DNS разрешение не используется.
Invalid chain/hostname, redirects, oversized/compressed/invalid responses и foreign scope fail closed.
TLS manager origin — trusted operator configuration, не admin/model/producer input. Generic application
container egress firewall для production остаётся отдельным F23 deployment gate; это не закрытие13.2.4/5.

## Секреты и операции

[Crypto inventory](f18-crypto-inventory.json). Setup сохраняет existing ring/credentials и делает CAS0
только для отсутствующих records. Root/unseal/CA private key остаются у host operator; приложения
получают только CA public и service-specific token. Test producer получает свои synthetic credentials,
но не manager root. Service policies перечисляют только два зарегистрированных synthetic tenant/connector пути. Новый connector требует явного operator provisioning/ACL; arbitrary record path не открывается wildcard policy. Tenant-scoped policy отдельно проверена против второго tenant. Tokens истекают через1h, fail closed без file credential fallback. Явный setup
обновляет short-lived tokens; это не rotation connector keys.

Manager drill отдельно проверяет per-service и cross-tenant ACL, overlap h1/h2, retirement h1,
успешность h2, обработку уже принятых h1 jobs после retirement, CAS restoration и revoked token denial.
Обновление webhook record использует текущую KV-v2 version; нельзя молча перезаписывать новый ring.
При компрометации: disable connector, отозвать service token/старый kid, установить новый ring оператором,
проверить чужие scopes/audit и только затем включить config новой CAS version. Retirement действует при следующем manager fetch; уже начавшаяся проверка может завершиться в пределах HTTP deadline2s. Для немедленного административного барьера сначала disable (сериализованный config lock), затем retirement/re-enable. Receipt уже принятого
события сохраняется, pending при disabled quarantines. Restore manager использует принятый F17 paired
backup procedure; real vendor credentials и production recovery не заявлены.

## Проверки и ASVS

Основной код: `integrations/{contracts,egress,executor,secrets,service}.py`, admin/ingress routes,
MCP platform, CLI ingress worker с отдельным settings class (без business/MCP/manager credentials), migration0019. Реальные transport tests: `test_adapter_platform.py`;
TLS child API/simulator и kill boundaries существуют только в `tests/`. Подмена HTTP клиента не заменяет
позитивные реальные TLS/manager/DB проверки. Отдельные address/DNS policy tests используют controlled
resolver для проверки pinning, а simulator действительно принимает HTTPS request.

[Evidence](evidence/f18/README.md), [checks](evidence/f18/checks.json). SEC-04/09 плюс SEC-01/10:
scoped ASVS contributions добавляются без изменения253 inherited rows/owners/baselines/N/A и без
whole-requirement closure. Backend/browser/process/native TLS/MFA и supply-chain результаты считаются
принятыми только по фактически прошедшим текущим F18 reports; F17 reports остаются историческими.

Primary design references: [OWASP SSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
(all-address allowlist, redirects off и network layer), [OpenBao KV v2](https://openbao.org/api-docs/secret/kv/kv-v2/)
(versioned records/CAS). ASVS baseline pinned в repository; ссылки не заменяют requirement-specific evidence.
