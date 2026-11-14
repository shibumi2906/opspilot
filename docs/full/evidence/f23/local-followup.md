# Продолжение локальных проверок F20–F23

База `881ab33`, отдельный Full checkout. Без Jira, push, платных вызовов
и развёртывания пилота.

- **F20.** Локальный SQLite-симулятор сохраняет receipt до вызова, допускает
  одну отправку на tenant/operation, проверяет точную цель issue/comment и
  использует существующие правила reconciliation. 27 тестов payload/preflight/
  verification/simulator прошли, включая потерю ответа, конкурирующие
  повторы и сбой после сохранения receipt. Транспорт, PostgreSQL receipts,
  production grants и интеграция MCP остаются открыты.
- **F21.** Рецепт отдельного образа manager обновлён до x/net 0.62.0. Build
  подтвердил upgrade модуля, но первая сборка завершилась ошибкой DNS
  Go proxy. Повтор прерван недоступностью Docker Engine. Образ и его scan
  ещё предстоит подтвердить. Зависимые проверки реального F20 открыты.
- **F22.** GitHub API доступен на чтение. На ветке Full удалённый HEAD
  `629ab24b5eef4c60e1b1112e770fd6af5be42a6c`. Список зарегистрированных
  workflow содержит только `ci.yml`. Запуск F22 не найден, существующий Full F09
  завершился ошибкой. Подтверждение F22 на нужном SHA требует workflow,
  доступного для запуска в GitHub. Оценки владельца открыты.
- **F23.** Подготовлены команды для свежего TLS/OIDC/MFA и для проверки
  восстановленного воркера с отдельной внутренней сетью. Две новые
  попытки синтетической подготовки не дошли до принятого smoke:
  один запуск не достиг approval, другой завершился `unknown_outcome`.
  TLS-стенд r2 дошёл до healthy PostgreSQL и Redis. Дальше Docker Desktop
  возвращал HTTP 500 даже на version, а backend фиксировал no route to host
  до Linux Engine. Прохождение браузера, воркера, полный локальный замер
  и остановку TLS-контейнеров подтвердить не удалось. Результат r3 сохранён.

Изоляция MVP подтверждена до сборок. Текущий Docker-сбой не позволяет
выполнить финальную сверку ресурсов и проверить состояние всех контейнеров.

## После восстановления Docker Desktop

- F23 TLS r3 прошёл 8 TLS probes и 14 браузерных проверок, включая OIDC,
  отклонение неверного OTP, отдельное MFA-согласование и отзыв сессии.
  [TLS](tls-r3/tls-probes.json), [браузер](tls-r3/browser.json).
- F23 recovery r7 заново создал fixture и зашифрованную копию. На первой
  восстановленной БД без сети 57 таблиц совпали за 18,23 с после готовности
  PostgreSQL. На второй синтетической копии во внутренней сети replay
  завершённой операции дал 0 новых тикетов, а согласованный pending run
  возобновился и дал ровно 1 тикет. Время от начала подготовки внутренней
  сети до worker smoke — 25,51 с. PostgreSQL и manager были заранее готовы.
  [БД](opspilot-full-test-f23-r7/recovery.json),
  [воркер](opspilot-full-test-f23-r7/recovery-worker.json).
- Изоляция MVP прошла до и после обоих принятых запусков. Целевые
  live TLS/OIDC/MFA и полный RTO остаются открыты.
- После перезапуска третья сборка manager снова остановилась на DNS
  внутри Docker при загрузке Go-модулей с proxy.golang.org. DNS хоста
  разрешает этот адрес. Скан исправленного образа не состоялся.
  Повторная итоговая проверка MVP прошла, запущенных контейнеров F23 нет.
### 14 ноября — продолжение со старым токеном

[Повторный preflight](../f20/jira-preflight-2026-11-14.json) подтвердил старый
токен и права KAN, но project/metadata/search/userinfo вернули scope mismatch.
[Read probes](../f20/jira-read-probes-2026-11-14.json). Jira write requests 0.
Повторные 27 локальных проверок Jira passed.

Исправленный manager собран из pinned OpenBao2.7.2. Binary version
opspilot-f17.2, build modules x/net0.62.0. Образ
sha256:2e8154d114ef69a86c2d39c2813e4725c96cabbddd2be7faf791a0aa87f55d76.
Сборка использовала --add-host для Go proxy, адрес разрешён локально, TLS
и модульные checksums оставались включены. В build helper добавлена опция
ResolveGoProxyOnHost для повторения.

Стэнд r8 использовал новый manager. Backup/restore57 tables, pending interrupt
и receipt прошли. Worker smoke дал committed extra tickets0, pending new tickets1.
Measured22.86 seconds охватывает подготовку внутренней сети, restore и worker
smoke с заранее готовыми PostgreSQL и manager. [Evidence](opspilot-full-test-f23-r8/recovery-worker.json).
RTO целевого пилота, remote CI и owner item review остаются открыты.

### Исправленный manager — 14 ноября

Свежий Trivy scan образа manager:f23 дал HIGH/CRITICAL0.
[Скан и идентичность](manager-nov14/checks.json),
[raw scan](manager-nov14/manager-image.json).
Known CVE-2026-78661 исправлена в новом образе с x/net0.62.0.
Новый manager функционально проверен в r8. Исторический f17 image и прежние
F21 evidence сохранены. Перевод прежних окружений на этот образ выполняется
как отдельный rollout с их собственными проверками.
