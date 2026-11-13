# F23 — результаты локальной репетиции

- [Процедура и границы проверки](../../f23-pilot-runbook.md).
- [Восстановление и откат](recovery.json).
- [Изоляция MVP до запуска](mvp-before.json) и [после остановки](mvp-after.json).
- [Проверки SEC-01/10](security.json).

В fixture использованы приложение, scripted LLM, локальный MCP, PostgreSQL и
отдельный TLS manager. HTTP approval проверен через ASGI с синтетическими
сессиями. Browser OIDC login, MFA и переключение реального трафика открыты.
Повтор решения проверен на исходной fixture. На восстановленной копии
сверены persisted receipt и checkpoint, runtime replay остаётся открытым.
F20–F22 и live F23 остаются blocked.

Принятый запуск: `./scripts/test-full-f23.ps1 -Project opspilot-full-test-f23-r3 -Subnet 39`.
Копия 624 460 байт. Неверный ключ отклонён. Совпали количество строк и SHA-256
57 таблиц. Восстановление и SQL-сверка заняли 16,94 с после запуска пустой БД.
На кандидате подтверждена схема 0021 и новая функция admission. На recovery
подтверждена схема 0020 и прежняя функция. Recovery volume отдельный, сеть none,
роли приложения NOLOGIN, default_transaction_read_only включён.
Изоляция MVP прошла до и после. Все контейнеры F23 остановлены. Внешних
connector/model вызовов и push не было.

Проверка Compose overlay выполнена через `docker compose config --quiet`
с фиктивными HTTPS origin/issuer и digest. Runtime целевого overlay
остаётся непроверенным. Проверка scoped secrets/logs использовала
`scripts/check-full-f23-security.py opspilot-full-test-f23-r3`.
