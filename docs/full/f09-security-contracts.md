# F09 — решения безопасности до migration

Scope: один исполняемый create_ticket intent; multi-action executor и новые tools не вводятся.
`workflow.actions` сохраняется как compatibility storage immutable revisions (id = revision_id).
Новая logical_actions отделяет intent/current_revision/version от immutable payload. Run uniqueness
у revisions снимается; F09 graph использует один logical intent, F11 расширит bounded plan.

## Trust boundaries / угрозы

Browser получает только revision IDs/version/hash/TTL, посылает typed decision/revision command.
BFF проверяет fresh MFA, approver/operator scope и CSRF. LLM предлагает grounded payload, не grants.
Worker разрешён persisted actor/role, lease/epoch; Core выдаёт отдельный Ed25519 grant только после
persisted approval. MCP знает только public verification ring и domain DSN, независимо проверяет
claims/registry/approval/current revision/roles/self approval/DB clock/fence в write transaction.
Угрозы: tampered payload/target, confused deputy, stale approval/revision/role, JWT key confusion,
replay, lost decision/write response, concurrent revision/expiry/decision/cancel/stale worker.
Session token, service context и execution grant — разные credentials/purposes/key rings.

## Canonical revision и времена

Canonical JSON UTF-8, sorted keys, compact separators, finite strict typed TicketProposal.
Hash связывает schema v1, logical/revision IDs, revision number/plan version, tenant/run/customer,
create_ticket/local backend + connector, exact arguments, evidence refs, bounded preconditions,
risk/dependencies и DB-issued expiry. Payload immutable DB trigger; execution receipt отдельно mutable.
Approval expires через 15 минут (configurable). DB clock authoritative; request expected_version
strict integer. Повтор того же решения/version возвращает сохранённое состояние; opposite/stale 409,
expired 410. Новая revision supersedes неисполненное старое согласие; succeeded/unknown не редактируются.

## Keys / secret-ref contract

Grant ring: grant-current/grant-next Ed25519 slots; actual immutable kid = slot + SHA-256 public-key DER, purpose execution-grant-v1; issuer/audience отделены
от service-context. Только worker issuer получает grant private files; API/BFF получает только service-context keys, MCP — public grants.json; active kid configurable,
retired/missing key fail closed. Contract для F17 manager: secret ref -> purpose-bound private key,
version/kid, explicit permissions, rotation/compromise/recovery; file provider — только local adapter.
TTL grant ≤60 s и ≤ approval TTL; registry хранит jti/bindings/expiry/consumption, не JWT.
Новый epoch требует нового grant; old grant не разрешает новую запись. Unique revision receipt
и consumed jti проверяются атомарно; committed result читается без нового эффекта.

## Data classification / audit contract

Proposal/evidence/preconditions: tenant confidential, могут содержать PII; public DTO allowlist.
Keys/JWT/session/credentials: secret, запрещены browser/model/checkpoint/log/audit/export.
Revision/approval/grant jti/hash/actor/kid/epoch/reason/timestamps: restricted security metadata.
Events: revision proposed/superseded, approval decided/expired/revoked, grant denied/issued/consumed;
allowlisted IDs/hash/status only, append-only workflow audit/outbox. Payload/text/JWT не копировать.
F17 retention: active/pending/unknown сохраняются; tombstones/receipt binding переживают replay window;
tenant-scoped export/minimization, deletion и backup boundaries проектируются с этими IDs.

Это локальные F09 контракты SEC-01/02/03/04/05/06. Managed manager, protected collector,
IdP administrative operations и deployment остаются соответствующим этапам, полный L2 NOT_MET.

## Field / operation permissions

Operator-владелец run может менять только title/description/priority неисполненного intent;
customer_id/evidence_ids берутся из исходного grounded proposal и не меняются human edit.
Максимум 10 revisions; plan_version в линейном F09 intent повышается с revision; DAG вводится F11. Pending/approved можно supersede;
rejected/expired/revoked и succeeded/unknown закрыты для редактирования. Иной tenant/owner — 404.
Approver с fresh MFA принимает/отклоняет точную revision/version; только автор согласия
может его отозвать до effect. Политика self approval проверяется Core и MCP заново.
CLI не обходит hardened identity. Согласие старой ревизии не переносится на новую.
API contract change: expected_version обязателен, bool/string/float не принимаются.

## Scope review и deferred controls

Baseline matrix и 253 назначенных владельца/этапа сохраняются. Изменённые F09 поверхности:
V2 input/business flow, V8 object/field/tenant authorization, V9 purpose-bound tokens,
V11 key/hash contracts, V14 confidential proposal, V16 security metadata.
Дизайн новых grants не делает N/A протоколы приложения: GraphQL/WebSocket/file upload/media
не добавлены; их conditional N/A требует повторного review при расширении и owner review F24.
OAuth/OIDC/fresh MFA остаются обязательными: внешний IdP проверяется локальным TLS lab,
production IdP recovery/enrollment/admin MFA — SEC-02/F23. Нет production acceptance в F09.
Manager ACL/rotation recovery — SEC-04/F17/F23; retention/delete/export — SEC-05/F17;
protected collector/error logs — SEC-06/F16/F23. Это конкретные будущие gates, не pass.
Новые adapters F10/F18–20, DAG F11 и freshness F12 обязаны переиспользовать exact grant binding.

## Supply chain / remediation contract (SEC-10)

До локального stage done: locked dependency audits и scanner pinned by digest; runtime app/web
проверяются на OS и language findings. HIGH/CRITICAL блокируют stage/release, известная
package vulnerability также блокирует dependency gate. Отсутствие базы/ошибка scanner — fail.
Требования к исправлению: critical/exploited — triage в 24 часа, исправление до следующего
release и не позже 48 часов; high — до release и в 7 дней; medium — 30 дней; low — 90 дней.
Владелец: исполнитель соответствующего stage; эксплуатационный владелец назначается F23.
Для каждого finding сохраняются CVE/package/version/fix, scope, deadline и повторный scan.
Risk acceptance не превращает finding в pass. Библиотеки обновляются минимум ежемесячно,
security advisories проверяются при каждом stage и перед release. Источники: locked PyPI/npm,
официальные digest-pinned container images, pinned scanner. SBOM/provenance всего deployment,
registry signing и непрерывный мониторинг остаются SEC-10/F17/F23; F09 scan не заменяет их.


## F09 change gate mapping

| Package | F09 delivered contract / проверка | Оставшийся owner gate |
| --- | --- | --- |
| SEC-01 | Trust boundaries, abuse cases, permissions/classification, 253 backlog scope refs | Full requirement review / owner N/A F24, revised with each feature |
| SEC-02 | Fresh-MFA approval preserved; separate approver in real local IdP lab | Session admin UI F13–14, IdP lifecycle/admin operations F23 |
| SEC-03 | Canonical immutable revision, TTL, signed persisted grant, Core+MCP live auth, atomic receipt/fence/replay/races | New tools F10, DAG F11, freshness F12 recheck mandatory |
| SEC-04 | Independent Ed25519 ring, immutable key generation ID, provider interface, least-key mounts | Managed manager/compromise/recovery F17/F23 |
| SEC-05 | Confidential payload/secret metadata boundary; grants never public DTO/model/checkpoint | Retention/export/delete/backup F17 |
| SEC-06 | Issued/consumed/revoked/current revision DB audit/outbox, denial safe reason | Collector protection/redaction/error log retention F16/F23 |
| SEC-10 | Pinned scanner, package audits, app/web OS scan and remediation policy | Entire deployment inventory/provenance and operational monitoring F17/F23 |
