# Face Moment — выбранные архитектурные улучшения

## 1. Не показывать запоздавший результат предыдущего поиска

SpaPromoClient принимает realtime response только тогда, когда его
`(spa_id, attempt_id)` всё ещё соответствует активной попытке и client state
остаётся `searching`. Ответ завершённой, отменённой или заменённой попытки
молча отбрасывается без Promo rendering, success cooldown и display
acknowledgement.

Отдельные `capture_id`, server cancellation protocol и новый durable state не
нужны. Сервер может завершить уже начатую работу, но невостребованный result
остаётся `unconfirmed` и очищается по обычным TTL/retention rules.

Почему именно так: timeout или network delay могут вернуть корректный результат
уже после перехода display к рекламе или следующему посетителю. Проверка
активного `attempt_id` закрывает этот race минимальным client-side guard и не
усложняет realtime lifecycle.

## 2. Использовать стандартные HTTP errors без собственного error framework

Технические ошибки выражаются обычными HTTP statuses:

- `401` — отсутствующая или недействительная authentication;
- `403` — недостаточно прав;
- `413` — превышен допустимый payload;
- `422` — validation error;
- `429` — rate limit;
- `5xx` — внутренняя или upstream-ошибка.

Ожидаемые результаты корректно принятого capture/search request, например
`busy`, `deadline`, `unacceptable_query` и `insufficient_results`, остаются
небольшим domain outcome enum и не превращаются в transport errors. Клиент
принимает решения по status/outcome и не зависит от текста ответа `5xx`.

Почему именно так: стандартное разделение transport errors и business outcomes
упрощает backend, client logic, логи и contract-тесты. Собственный error
framework добавил бы форматы, mapping и поддержку без сопоставимой пользы для
одного backend.

## 3. Одна PostgreSQL schema и один поток migrations

Весь modular monolith использует одну PostgreSQL schema, один SQLAlchemy
`Base/MetaData`, одну Alembic configuration и один последовательный migration
stream. Таблицы и repositories остаются в code packages своих capability
slices; общая schema не разрешает прямые foreign writes и не меняет
slice-level ownership.

Отдельные PostgreSQL schemas, DB users и ACL per slice не создаются. Foreign
keys и `ON DELETE` rules задаются осознанно: database cascade не должен
пересекать ownership boundary и, в частности, удалять core Attempts или
diagnostic evidence вместе с Photo.

Почему именно так: slices разделяют бизнес-ответственность внутри одного
deployable, а не имитируют микросервисы в общей БД. Одна schema и migration
stream упрощают shared transactions, joins, локальную разработку и deployment.
Обычные конфликты migrations между ветками дешевле, чем постоянная сложность
нескольких schemas и независимых migration pipelines.
