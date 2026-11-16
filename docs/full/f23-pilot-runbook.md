# F23 — локальная подготовка пилота

## Продолжение 16 ноября: выбран локальный TLS target

Актуальный профиль и отдельные результаты:
[local-pilot-20261116](evidence/f23/local-pilot-20261116/README.md).
Последний accepted functional project — `opspilot-full-test-f23-recovery4`.
Все6 exact runtime images raw H/C0; полный cold restore63.88s на этой машине с
preloaded images,59-table match и browser approval/admin MFA. Это заменяет только
исторические ограничения о невыбранном target и отсутствии local browser/manager restore.
Full/L2 остаются NOT_MET: host encryption/OS assessment, operational backup/retention,
final SHA CI и requirement-specific ASVS review открыты.

One-time preparation: `test-full-f23-local-pilot.ps1 -Mode Prepare` создаёт новый
project и три свободные подсети; существующие credentials не пересоздавать.
`-Mode Start` требует уже запущенный и unsealed manager с актуальными короткими токенами.
`-Mode Probe`/`Fixture` пишут уникальные отчёты. AdminMfa enrollment не повторять
после verified state. Для повторных репетиций выбирать новые project/subnets.
Backup/restore runner сохраняет источники и failed instances; архив и ключи остаются
ignored. Прежде чем включать egress восстановленной среды, сверить receipts и
неизвестные операции с доступным оригиналом. Текущий lab Jira не подключает.

Ниже сохранён исходный исторический runbook; новые разрешения/результаты выше имеют приоритет.

Рабочая копия Ops, ветка `codex/opspilot-full`, исходный коммит `d17b486`.
Локальная репетиция использует отдельный Compose project, синтетический GreenShop
и scripted LLM. Для локального восстановления PostgreSQL запускается без сети,
с отдельным томом и ролями приложения без LOGIN. Домен, issuer и target пилота
ожидают согласования владельца. Локальный TLS-референс использует
`app.opspilot.localhost` и `https://idp.opspilot.localhost:8543/realms/opspilot`
(точные origin и issuer берутся из native TLS конфигурации).

## Локальная репетиция

Из Ops с работающим Docker Desktop и существующим окружением `.venv`:

~~~powershell
./scripts/test-full-f23.ps1 -Project opspilot-full-test-f23-r3 -Subnet 39
~~~

Выберите новый проект и свободную подсеть. Команда проверяет fingerprints MVP,
закрепляет локальные ID образов, генерирует отдельные DB-пароли, создаёт синтетические
pending approval и committed ticket через приложение, останавливает процессы записи
и делает единый логический dump PostgreSQL. Ключ и зашифрованная копия находятся в
разных каталогах под `.tools/f23/<project>`. Они хранятся на одном локальном хосте.
Копия содержит таблицы domain, workflow, identity, integrations и checkpoints.
Роли в recovery создаются отдельно. Развёртывание IdP и manager, их данные и ключи
в этот dump не входят. Скрипт рассчитан на малую БД и держит plaintext dump в памяти.

Репетиция применяет миграцию `0020_prometheus → 0021_worker_admission` на
исходном лабораторном томе и восстанавливает `0020_prometheus` в пустую БД
`opspilot_full_recovered`. Проверяются pending interrupt, receipt и ticket,
логические хэши и старая версия функции admission. Исходная кандидатная БД
сохраняется. Стенд останавливается, логи и тома остаются для проверки. Показатель
времени охватывает восстановление и SQL-сверку, а RTO на целевой среде включает
выдачу ключа, перенос копии, загрузку образов, доступность зависимостей и smoke.

## Проект runbook для согласованного target

1. Выберите хост, DNS, HTTPS origin и OIDC issuer. Используйте native TLS topology
   из `infra/security/generate_local.py` и reverse proxy из
   `infra/security/nginx.conf` как конфигурационный референс. Подготовьте целевую
   Compose-конфигурацию с проверяемыми TLS CA/SAN, отдельными сетями для ingress,
   приложения и данных, и deny-by-default для egress. Разрешите только
   согласованные destinations. Публикуйте HTTPS edge, IdP доступен по согласованному
   HTTPS issuer. Используйте non-root образ для proxy и отдельные writable tmpfs
   для его runtime. Локальный генератор выпускает тестовые CA и пользователей.
2. Наложите `compose.full.f23-pilot.yaml` на целевую конфигурацию. Используйте
   ссылки `registry/repository@sha256:…`, заранее загруженные на хост, и храните
   предыдущие digest, schema compatibility и release manifest. Проверьте результат
   `docker compose config` в закрытом окружении. Подтвердите DNS, CA, certificate
   expiry, сетевые границы и health, CPU/memory, service identities, protected logs,
   SBOM, scan точных образов и OS. Для IdP проверьте отдельную админскую MFA,
   recovery, reset, factor notifications, revoke и approval step-up.
3. Доставляйте scoped DSN и signing material через read-only secret files
   (`SECRET_FILES`), manager tokens через `SECRET_MANAGER_TOKEN_FILE`. Права и
   короткоживущие токены выдаются отдельно каждому сервису. Ключи backup храните в
   отдельном контуре с журналом доступа и регулярной проверкой rotation/revoke.
   Настройте шифрование дисков и отдельно защищённый off-host backup.
4. Перед релизом перекройте входящие запросы записи и остановите intake.
   Дождитесь завершения активных leases и сохранения pending checkpoints.
   Сверьте operations in-flight/unknown по receipts, сделайте pre-migration backup.
   Запустите миграцию отдельным admin job. Затем API и один совместимый worker,
   проверьте health и browser login/approval, потом включайте остальные workers.
5. При сбое снова перекройте intake и egress, остановите workers. Сохраните
   candidate volume для reconciliation. При совместимой схеме верните
   предыдущие digest. При несовместимой схеме восстановите pre-migration backup
   в новый instance, сверив schema, pending checkpoints и receipts. Сопоставьте
   операции после точки backup с кандидатной БД и доступным внешним аудитом.
   Получите подтверждение оператора перед переключением DSN/маршрута и
   отдельное подтверждение перед включением workers и write egress.
6. Настройте backup не реже одного раза за 24 часа, 7 ежедневных и 4 еженедельных
   копии. Проверяйте восстановление и отзыв доступа к backup регулярно.
   Целевой измеренный RTO ≤60 минут. Перед live-приёмкой выполните полное
   восстановление IdP/manager по их независимым процедурам.

## Условия выпуска

- F20 — sandbox Jira, авторизованный write/read, граница одной попытки и
  reconciliation остаются открыты. Не включать Jira egress на recovery.
- F21 — локальные load/soak/fault checks пройдены в их scope. Открыты границы
  F20 и manager HIGH CVE-2026-78661.
- F22 — scripted 50/50 и MVP regression 12/12 исторические. Основная real
  серия 78/90, у 12 неудач есть успешные диагностические повторы.
  Ожидаются оценки отдельных утверждений и подтверждённый remote CI.
- F23 live — fresh staging, browser login/approval, service PKI, IdP MFA,
  managed secrets и rotation/revoke, актуальные image/OS scan, protected
  logs/alerts, off-host storage/retention и end-to-end rollback/RTO.
  Полный ASVS L2 и Pilot остаются NOT_MET.
