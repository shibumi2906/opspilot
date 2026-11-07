# ASVS L2 — обязательные задачи реализации Full

27 октября 2026. Область: F01–F24 Full, OWASP ASVS **5.0.0**, L1+L2 (253 требования).
Основание: запрос владельца включить безопасность в задачи реализации, baseline `48486d0`.
Каноническая очередь — [Full tracker](../full-version-status.md); этот план дополняет
[спецификацию](../../OpsPilot_Full_Project_Specification.md), а не создаёт параллельную очередь.
F01–F08 сохраняют исторический done. Следующий этап — F09 вместе с его security-задачами.
**Полный L2 остаётся NOT_MET до закрытия всей применимой матрицы.**

## Как выполнять без поздней переделки

1. До проектирования этапа прочитать его security-строку ниже и назначенные ему требования
   [requirement backlog](asvs-l2-requirement-backlog.json). Исполнитель этапа отвечает и за безопасность.
2. Контракты, data classification, secret refs, security events и key/version semantics
   определить при первом использовании; не откладывать их проектирование до F17/F23.
3. Использовать baseline `48486d0`: hardened TLS/MFA/session/limits/headers/DOM controls
   сохраняются. Redis/SSE/adapters не заменяют их более слабым поведением.
4. Для каждого затронутого ASVS ID записать implementation/evidence/review status, source SHA,
   профиль, команды и результаты; если контроль уже реализован — проверить переиспользование,
   не переписывать его и не объявлять старое evidence свежим.
5. F-stage получает done только после своих функциональных и security gates. Нужные этому
   gate внешние данные отсутствуют — gate blocked; независимая локальная работа продолжается.
   Production target не блокирует F09, если его gate полностью локальный; он обязателен для F23.
6. `supported`, N/A и verified local из baseline не считаются независимым ASVS pass.
   N/A требует основания по фактическому scope и review владельца; новая функция требует пересмотра. При изменении scope открыть повторную проверку
   соответствующей строки до done этапа; прежнее evidence сохранить с его SHA/профилем.
   Risk acceptance, известная CVE или отсутствие функции не превращают требование в pass/N/A.
7. В каждом stage commit обновлять канонический tracker, соответствующие backlog items и evidence.
   Для изменения этих требований нужен явный rationale; молчаливое исключение gate запрещено.

## Пакеты работ

Статус SEC-00 — done в ограниченном local scope. SEC-01/02/03/04/05/06/10 — `in_progress` (F09 contracts и локальная реализация), остальные — `not_started`;
это новые задачи, а не подтверждение выполнения соответствующих норм.
Подзадачи могут закрываться поэтапно; пакет целиком — после всех его gates.

| ID | Первое решение / основной этап закрытия | Задача и критерий приёмки |
| --- | --- | --- |
| SEC-00 | F01–F08 / baseline `48486d0` | Сохранять локальные TLS/MFA/session/admission/audit controls. Evidence и ограничения: [hardening tracker](hardening/status.md). Не переносить local verified на production. |
| SEC-01 | до схемы F09 / F09, итог F24 | Обновить threat model и trust boundaries API/worker/MCP/IdP/LLM/Redis/adapters; data flows, abuse cases, security assumptions и ответственность провайдеров. Review всех 253 IDs и conditional N/A; каждое требование имеет accountable stage, тест/evidence или конкретный blocker. При каждом расширении scope пересматривать модель. |
| SEC-02 | F09 / F13–F14; IdP live F23 | Identity/session policy: свежая MFA на approval и admin actions, absolute/idle/parallel limits, revoke/logout/disable и role changes, session inventory/revoke UI. Закрыть IdP password blocklist, recovery/reset, MFA enrollment/removal notifications и MFA административного plane. Проверить IdP outage/fail-closed, reset/disable/revoke-all и SSE revocation; synthetic master bootstrap account не допускается как production admin. |
| SEC-03 | до schema/grant F09 / F09–F12 | Exact authorization: canonical payload/hash/schema/revision/tenant/actor/tool/audience/key-id/TTL, immutable approval и scope-checked persisted grant; replay/revoke/expiry/fence, независимая проверка MCP. Права перепроверяются перед effect; новая revision не наследует старое согласие. Negative tests прямого MCP, confused deputy, races и mixed plans дают 0 unauthorized writes. |
| SEC-04 | secret/key contract F09 / F17, connector gates F18–F20, live F23 | Ввести provider-neutral secret refs и crypto/key inventory: purpose/owner/algorithm/kid/version/TTL/rotation/compromise/recovery. Выбрать и подключить реальный secrets manager с per-service/tenant ACL, short-lived access и audit; file mounts lab не закрывают задачу. Разделить signing/encryption/provider credentials, проверить отказ/rotation/revoke с in-flight jobs и compromise drill; действующие секреты не возвращаются UI/export. |
| SEC-05 | event schema F09 / F16; Core F17, live F23 | До новых mutations определить security events и redaction для auth/role/grant/limits/TLS/config/export. Затем отдельный защищённый collector, integrity/access/retention/clock/correlation, bounded fallback и работающие alerts. Проверить sentinel secrets в access/error logs, traces, events, exports; nginx error diagnostics сохранять, настроить redaction/защиту, не отключать ради зелёного теста. Tamper/outage/alert evidence обязательны. |
| SEC-06 | до новых payloads F09–F10 / F17, storage F23 | Классифицировать request/evidence/checkpoint/receipt/audit/PII/credential data; зафиксировать минимизацию и field allowlists. Спроектировать retention/export/delete/tombstone/backup boundaries сразу со схемой. Реализовать dry-run/delete и tenant-scoped export, сохранить pending/unknown и anti-replay tombstones; настроить encryption at rest и отдельные backup keys, проверить restore и удаление с учётом backup retention. |
| SEC-07 | bounded contracts F11/F13 / F15, нагрузка F21 | Сохранить durable counters и atomic admission baseline; добавить quotas/reservations/fairness, SSE/connector/cardinality/body/concurrency bounds. Redis outage/eviction/restart не сбрасывает лимиты и не делает write unlimited; cache не источник authorization/approval/freshness. Проверить concurrent exhaustion, key poisoning/cross-tenant scope и bounded degradation. |
| SEC-08 | новые render/API fields F10 / F13–F14 | Strict DTO/canonical decoding и output encoding, безопасные content types/URLs, CSP/HSTS/cookies/origin/CSRF/no-store. Authenticated SSE/cursor scope, bounded replay/backpressure и revoke ≤30 s. Проверить XSS/DOM/URLs, роли/tenant, logout/expiry/offline/403 и приватные history/inbox/admin/export views; статус Sign in не подтверждает server logout раньше ответа. |
| SEC-09 | credential/egress interfaces до F18 / F18–F20 | Connector tenant/destination/scope binding, secret refs и least privilege; SSRF/DNS rebinding/redirect/metadata/private-network policy и TLS peer verification. Webhook raw-body signature/timestamp/key rotation/replay/size limits, durable receipt/job. Проверить simulator adversarial cases и отдельно разрешённые Prometheus/Jira targets; внешние writes только по approval с reconciliation, без blind retry. |
| SEC-10 | gate с F09 / inventory F17, deploy artifacts F23 | CI gates для lock/config/secrets/dependency/SBOM и container/OS image scanning; pin/digest, provenance и обновление уязвимых транзитивных зависимостей. Назначить patch SLA и remediation workflow по severity. Сохранять scanners/DB versions/results; известные применимые vulnerabilities устранять/проверять, а не скрывать ignore. Package scan не заменяет image/OS scan. |
| SEC-11 | cases при каждой функции / F21–F22 | Requirement-specific negative/fault/load tests: tenant/role/session/grant/expiry/replay/cancel/SSRF/injection/secrets/limits, реальные transport/DB/process boundaries. Включить security invariants в 50 Full evals и CI; setup failures/holdout/real spend отражать честно. Нет unauthorized writes/leaks/false verified success; mocks не закрывают live gates. |
| SEC-12 | deployment contracts с F09 / F23–F24 | Hardened deployment с реальными DNS/PKI/IdP/manager, service TLS, private networks, non-root/resource limits, protected diagnostics, storage и backup encryption. Проверить expiry/hostname/CA/rotation, свежий deploy, drain/rollback и restore в новый instance с egress/write disabled. Финально проверить все applicable L1+L2 и reviewed N/A на pinned deployment, CI run URL и MVP isolation; до этого release/L2 acceptance не done. |

## Обязательства по этапам

Общие SEC-01 scope review и SEC-10 change gate действуют на каждом этапе ниже.
Основной владелец требования в JSON не освобождает другие этапы от проверки затронутого контроля.

| Этап | Security-задачи и результат, необходимый до done |
| --- | --- |
| F09 | SEC-01/02/03/04/05/06: threat model; canonical grant/key/secret-ref/event/data contracts до migration; fresh MFA и negative authorization/replay/expiry tests. Реальный secrets manager пока не требуется, но интерфейс и границы полномочий уже обязательны. |
| F10 | SEC-03/06/08: exact field/recipient/ticket scope, классификация новых comment/inbox payloads, encoding/export/redaction rules и независимая MCP verification. |
| F11 | SEC-03/07: bounded DAG/action count, отдельные grants/approval waves, dependencies и запрет escalation/replay завершённых effects. |
| F12 | SEC-02/03/04: DB-time TTL/revocation/role changes/key overlap, uncached preconditions и bounded replan; race tests. |
| F13 | SEC-02/07/08: SSE token/cursor scope без URL secrets, expiry/logout/disable/revoke ≤30 s, connection/replay/backpressure limits и private DOM reset. |
| F14 | SEC-02/06/08: session/admin/recovery UX, tenant/role/connector ACL; secure rendering/headers/cookies/CSRF, export privacy и Playwright negative matrix. IdP-only политики требуют отдельного evidence. |
| F15 | SEC-07: durable bounded admission/cost/usage при Redis failure/restart, fair actor/tenant/global reservations; cache не authorization store. |
| F16 | SEC-05: protected collector/redaction/alerts, log integrity/access/time, bounded outage fallback; sentinel и tamper tests. |
| F17 | SEC-04/05/06/10: работающий manager + rotation/recovery drill, crypto inventory, retention/delete/export/tombstones, dependency/image inventory и согласованная patch policy; scoped Full Core security acceptance. |
| F18 | SEC-04/09: manager-backed connector refs/ACL до подключения vendors; signed durable ingress, key rotation/replay/SSRF/redirect/failure tests. |
| F19 | SEC-09: Prometheus least-privilege queries/ranges/cardinality/tenant/TLS/egress; redacted authorized staging evidence, не simulator вместо live. |
| F20 | SEC-03/09: Jira project/field/recipient scopes, exact grant/marker/verification, permission denial/lost response/reconciliation; разрешённые sandbox writes отдельно от faults simulator. |
| F21 | SEC-02/03/05/07/09/11: adversarial multi-API/worker/tenant fault/load/soak matrix с measured bounds и 0 leaks/unauthorized/duplicate writes. |
| F22 | SEC-10/11: security cases связаны с ASVS IDs, scripted release gates и честный real/holdout report; remote CI и real gate не объявляются пройденными без evidence. |
| F23 | SEC-02/04/05/06/09/10/12: IdP admin MFA, real manager/PKI/network/storage/logging/image scans; fresh deploy/rotation/backup/restore/rollback с безопасным egress. Нет выбранного target или разрешения — live gate blocked. |
| F24 | SEC-01/10/11/12: review всех 253 строк, evidence на release SHA/config/deployment, owner-reviewed N/A, отсутствие открытых applicable требований; release traceability, remote CI и сохранённый MVP. |

## Учёт требований и критерий полного L2

[JSON backlog](asvs-l2-requirement-backlog.json) содержит ровно 253 IDs исходной матрицы,
primary SEC owner, accountable F-stage, этап проектирования, текущий baseline assessment,
новый work status и поля реализации/evidence/review/blocker. `not_started` в этом файле —
статус новой requirement-specific проверки/доработки; он не отменяет сделанный local baseline.

Для requirement done нужны одновременно: реализация в нужном scope, положительная
requirement-specific проверка на указанной версии/профиле и review. Для N/A нужны rationale,
review владельца и подтверждённый scope; пустое evidence или inherited supported недостаточны.
Ни accepted risk, ни средний процент тестов не закрывают applicable ASVS requirement.
F17 принимает Core в его scope; F24 принимает весь Full Pilot и L2 только после F23.
Решения о публичном домене/IdP/manager/deployment принимаются до использования соответствующей
внешней зависимости; этот план не разрешает deploy, платные calls или внешние writes сам по себе.

F09 change review: [контракты и scope](../full/f09-security-contracts.md). Requirement backlog содержит F09 contributions отдельно от полного закрытия нормы. Финальные результаты текущего этапа записываются в его evidence; исторический baseline не перезаписывается.

F09 local change gate завершён: [измеренные проверки](../full/evidence/f09/checks.json). SEC packages сохраняют in_progress до всех своих будущих gates; вклад F09 отмечен отдельно в requirement backlog. Полный L2 остаётся NOT_MET.


F10 local change gate passed: [contracts](../full/f10-security-contracts.md),
[measured acceptance](../full/evidence/f10/checks.json). SEC-08 local implementation started;
package/whole-requirement closure remains with accountable owners. F10 contributions are recorded
separately in all affected backlog rows. Retention, managed storage/keys, deployment and complete
L2 acceptance remain their future gates; full L2 is NOT_MET.


F11 local change gate passed: [contracts](../full/f11-security-contracts.md),
[measured acceptance](../full/evidence/f11/checks.json). SEC-03/07 bound local DAG/approval waves,
per-action capability/dependency checks, durable verification quota and queue handoff are verified.
SEC-01/10 change review and scans also pass in this local scope. Full requirement closure,
remaining quotas/fairness, manager/storage/production controls remain accountable future work;
all253 requirement identities/baseline assessments are preserved and full L2 remains NOT_MET.


F12 local change gate passed: [contracts](../full/f12-security-contracts.md), [acceptance](../full/evidence/f12/checks.json). SEC-02/03/04: DB-time expiry/revoke/role checks, grant key overlap, uncached preconditions and bounded replacement consent; SEC-01/10 regression and supply-chain gates pass. All253 IDs/levels/baseline assessments/owners remain unchanged. No whole-norm or production L2 acceptance; full L2 remains NOT_MET.


F13 local change gate passed: [contracts](../full/f13-security-contracts.md),
[acceptance](../full/evidence/f13/checks.json). SEC-02/07/08: cookie-authenticated DB SSE,
session/actor/tenant/run-bound header cursors, uncached revocation and object authorization,
bounded replay/reset/send/connections with fail-closed reservation health, private DOM reset and
serialized snapshot recovery. Native TLS/MFA IdP-disable SSE revocation measured886ms; backend382,
browser17, queue5, fencing3, TLS8+13, scripted12 and SEC-01/10 supply-chain/regression gates pass.
All253 IDs/levels/baseline assessments/owners remain unchanged; no whole-norm closure. Full L2 NOT_MET.


F14 local change gate passed: [contracts](../full/f14-security-contracts.md),
[acceptance](../full/evidence/f14/checks.json). SEC-02/06/08 covers role/tenant-bound history,
recipient inbox, session/admin UX, connector CAS/freshness, safe rendering and bounded private
exports. Backend387, OIDC/browser21, queue5, fencing3, TLS8+MFA14 and distinct IdP policy4 pass;
IdP-disable SSE revocation605ms. SEC-01/10 includes raw OS/JAR scans and exact artifact applicability:
IdP raw4 HIGH util-linux source-attributed findings are retained; verified libuuid-only image
contains no affected libmount/nsenter code. No ignore, metadata removal or risk acceptance.
All253 protected identities/baseline assessments/owners/NA fields are preserved. Scoped reviews174
pass;103 primary rows retain whole-requirement verification open. Production recovery delivery,
factor notifications and administrator-plane MFA remain F23 obligations; full L2 NOT_MET.


F15 local change gate passed: [contracts](../full/f15-security-contracts.md), [acceptance](../full/evidence/f15/checks.json). SEC-07: PostgreSQL durable actor/tenant/global admission, fenced usage/reservations, fair worker caps and retry/crash accounting; HMAC-scoped disposable Redis cache with transactional invalidation and bounded authenticated TLS fallback. SEC-01/10 regression/supply-chain gates pass: backend402, browser22, queue5, fencing3, provider crash1, Redis restart1, native TLS8+Redis6+MFA14+IdP policy4, scripted eval12/12. App/web/Redis raw H/C0; IdP raw4 retained with exact-image applicable0 proof. All253 protected requirement fields remain;125 scoped reviews and1 primary contribution do not close whole norms. Full L2 remains NOT_MET.


F18 local change gate passed: [contracts](../full/f18-security-contracts.md),
[acceptance](../full/evidence/f18/checks.json). SEC-04/09 plus SEC-01/10 cover exact manager
credential/webhook scopes, synthetic registered HTTPS/IP pinning, bounded transport/breaker,
raw-body HMAC/key rotation/replay, durable observation receipts/jobs and least-privilege processor.
Transport33, backend486/44 specialized skips, unit200, browser24, queue5/fencing3, eval12/12;
native TLS/MFA plus positive ingress/verify-full DB/CLI, six runtime images raw H/C0, no secret matches.
All253 inherited requirement fields including F17 contributions remain exact;102 new scoped reviews
and5 primary local contributions do not close whole norms. SEC-09 is in_progress for the full
application: F19/F20 vendor and F23 production egress/TLS/deployment gates remain. Whole L2 NOT_MET.


## F19 local change gate; authorized staging deferred

Local fixed/read-only Prometheus queries, metadata/manager ACL, tenant mapping/RLS, bounded range/
cardinality/body/deadline, TLS/DNS/redirect/error and UI provenance are verified under
[scoped evidence](../full/evidence/f19/README.md). All253 inherited fields remain exact;85 scoped
contributions and5 primary reviews close no whole requirement. Original runtime2 HIGH fixed by
pinned source rebuild/x-net0.62.0; final raw H/C0; nonblocking MEDIUM/UNKNOWN retained in reports.
Native Prometheus Basic Auth has no label-level RLS; upstream staging isolation/gateway needs
review. User explicitly deferred staging target/access, so F19 overall blocked. F20/F23/whole L2
remain open. Main dev stays accepted F18/schema0019; schema0020 is isolated-test-only.
