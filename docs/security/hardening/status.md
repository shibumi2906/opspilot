# Security hardening tracker

Baseline: F08 `fe78a5c`, ASVS **5.0.0 L2**, local lab выбран пользователем.
**Локальный hardening baseline: done. Полный ASVS L2: NOT_MET — оставшиеся условия открыты.**
F01–F08 остаются done, F09 остаётся not_started.

| Пакет | Состояние | Доказательство |
| --- | --- | --- |
| TLS/host cookies/response policy | local verified | evidence/tls-probes.json, evidence/browser.json |
| Mandatory MFA + IdP account disable | local verified | evidence/browser.json |
| Session idle/parallel/revoke + tenant admin scope | verified | evidence/security-integration-final.log, evidence/security-unit-final.log |
| Atomic request/run admission + idempotency | verified | evidence/regression-verified.log, security integration/unit tests |
| Private DOM offline/online logout | verified | evidence/browser.json, evidence/e2e-verified.log |
| Structured audit and application SQL grants | local verified; external collector open | evidence/tls-probes.json |
| Python/npm package SCA and SBOM | no known package vulnerabilities in this scan | evidence/python-audit.json, evidence/npm-audit.json, *-sbom.json |
| Main Linux regression | 261 passed, 9 skipped | evidence/regression-verified.log |
| Added recent-auth/admin-scope checks | 19 security unit + 5 security integration passed | evidence/security-unit-final.log, evidence/security-integration-final.log |
| Browser regression | 12 passed | evidence/e2e-verified.log |
| Process queue / fencing | 5 / 3 passed | evidence/queue.log, evidence/fences.log |
| Scripted evals | 12 passed, safety gate true | evidence/evals/scripted.json |
| MVP isolation | source/env/head/images/volumes match | evidence/mvp-after.json |
| All-253 L2 acceptance / production operations | open | README.md, verification-overlay.json |

Основной прогон содержит существующие тесты; focused counts не складываются с ним.
9 skipped — отдельные process/restart сценарии; queue/fencing прогнаны отдельно,
API hard-restart scenario не включён этим прогоном.

Обнаруженные и исправленные проблемы: worker SELECT на identity.users заменён на
scope-checked definer function; unit fixtures отделены от development DSN environment;
logout очищает DOM сразу, а завершение server logout имеет отдельное состояние UI.
Начальные неуспешные логи `*-initial-*.log` сохранены как diagnostic history
(trailing whitespace нормализован при сохранении) и не считаются passing gates.
Docker engine 500/hang и transient loop1 I/O errors потребовали восстановления Desktop;
factory reset, удаление volumes и ремонт дискового образа не выполнялись.
Изоляция MVP после восстановления подтверждена повторным read-only fingerprint check.

Security lab проверен и остановлен после проверок. Обычный Full восстановлен с двумя workers;
для повторного старта lab используется `scripts/test-security-local.ps1 -SkipBuild`.
Production secret manager, защищённый log collector/redaction, data lifecycle/backup,
IdP administrative MFA/recovery/reset policy, image/OS SCA и независимая ASVS-проверка
остаются условиями полного L2, а не исключениями N/A.
