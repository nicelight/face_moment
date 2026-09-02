---
description: Evidence-based assessment of the first finding in the 2026-09-02 concise technical-debt report.
status: active
---
# Оценка finding «Docker-проверка может запускать устаревший код»

## Проверенный scope

Проверен только первый finding из
`PAPERCUTS/TECHDEBTS/tech-debt-2026-09-02.md`: текущие `Dockerfile` и
`compose.yaml`, фактический `face-moment:dev`, текущая реализация TASK-094 и
релевантные execution/verification reports FT-004, FT-005, FT-008 и FT-009.
Другие семь findings не переоценивались.

## Вердикт

Основной механизм подтверждён: обычный `docker compose run` сейчас способен
дать результат для другой версии Python-кода и tests, чем версия в рабочем
tree. Finding объективен и материален как debt достоверности verification
evidence.

Формулировка приоритета и причины требует уточнения:

- утверждение «самый важный» не является объективным свойством самого
  механизма; это обоснованный P1-приоритет только для работ, которые используют
  bare Compose command как доказательство текущего source;
- не любой последующий test теряет смысл: current-source read-only mount,
  успешный post-change rebuild, Node tests и другие проверки с явным
  provenance остаются валидными;
- stale image возникает прежде всего потому, что `docker compose run` без
  `--build` не выполняет build. Docker cache в `Dockerfile:11-13` не может быть
  причиной того, что build вообще не запускался;
- отдельно подтверждён усиливающий механизм: при настоящем rebuild изменение
  `src/` инвалидирует `RUN pip wheel .`, а эта команда снова разрешает
  application dependencies. Это делает rebuild дорогим и зависимым от сети,
  но является второй причиной, а не объяснением bare-run stale image.

## Evidence

- `compose.yaml:3-6,100-107` задаёт build/image, но не монтирует host source в
  backend; его volumes относятся только к runtime storage.
- `Dockerfile:11-13` копирует `src/` и строит wheel, а
  `Dockerfile:29-37` устанавливает wheel в runtime image и лишь затем копирует
  snapshot source/tests. У package entrypoints приоритет остаётся за
  установленным `site-packages`.
- Фактический `face-moment:dev` имеет image ID
  `sha256:7d3b83ef8220e7ffe4852f89894cdd312b73e12af3082e701c80969904419fba` и
  создан `2026-09-01T09:27:50Z`, до текущего commit TASK-094 от
  `2026-09-02T16:36:46+05:00`.
- Fresh bare probe через
  `docker compose run --rm --no-deps backend python -c ...` импортировал
  `/usr/local/lib/python3.11/site-packages/face_moment/...` и показал старые
  сигнатуры `emit_attempt_admitted(event_sink, attempt)` и
  `emit_attempt_terminal(event_sink, attempt)`.
- Тот же image с read-only mount и `PYTHONPATH=/workspace/src` импортировал
  текущий workspace и показал сигнатуры TASK-094 с `attempt_id`,
  `correlation_id` и `processing_status`. SHA-256 импортированных файлов
  совпал с файлами рабочего tree.
- `src/face_moment/promo/realtime_orchestration.py:248-273` и
  `src/face_moment/entrypoints/realtime.py:220-290` подтверждают primitive-only
  current-source handoff.
- `.tasks/TASK-078-T3-FT-005-W2/TASK-078-T3-FT-005-W2-S-EXECUTE-final-report-code-02.md:49-52`
  фиксирует прежний bare run: mypy проверил 67 старых source files, а pytest не
  увидел task-owned test path.
- `.tasks/TASK-094-T3-FT-009-W1/TASK-094-T3-FT-009-W1-S-VERIFY-final-report-docs-01.md:27-37`
  подтверждает, что TASK-094 не зависит от stale-image evidence: независимая
  проверка использовала current-source read-only mounts и прошла.
- `.tasks/TASK-089-T3-FT-008-W2/TASK-089-T3-FT-008-W2-S-EXECUTE-final-report-code-01.md:110-117`
  фиксирует три rebuild failure на внешнем download и вынужденную сборку
  отдельного current-source gate image.
- Локальный `docker compose run --help` подтверждает наличие явной опции
  `--build`; без неё build не является частью команды.

## Практический impact и необходимость закрытия

Закрытие необходимо до того, как bare `docker compose run` снова будет принят
как evidence текущей реализации. Иначе возможны как ложный GREEN по старому
коду и старым tests, так и ложный RED из-за отсутствующего нового модуля или
test path. Повторение в task reports показывает maintenance cost, а не только
единичный operator error.

Finding не блокирует уже выполненную проверку TASK-094 и не требует немедленно
останавливать работу, если каждый новый receipt явно использует current-source
mount либо успешный post-change image build. Поэтому относительная оценка —
`P1 для verification workflow`, но не безусловный repository-wide P0.

## Минимальное направление закрытия

1. Сделать один project-native gate command, который механически выбирает и
   показывает один из двух валидных provenance modes: read-only current-source
   mount с явным `PYTHONPATH` либо build перед run. Bare run без доказательства
   актуальности image не принимать как current-source evidence.
2. Для unit/mypy gates достаточно уже доказанного read-only mount; для проверки
   packaged runtime нужен успешный post-change build и зафиксированный image
   digest или другой однозначный source marker.
3. Разделение dependency и application wheel caching в Dockerfile имеет смысл
   как последующий небольшой repair, если network-sensitive rebuild остаётся
   частью обязательного gate. Оно не требуется, чтобы сначала устранить
   неоднозначность bare-run evidence.

Новый build system, массовая правка старых task cards или сложная система
release metadata для закрытия finding не нужны.

## Неопределённость

Не измерялись среднее время rebuild и частота сетевых failures; поэтому
стоимость cache refactor нельзя ранжировать точнее. Текущего evidence достаточно
для подтверждения source/image mismatch и необходимости provenance guard.

## Результат закрытия 2026-09-02

Принят local-first repair без source mounts и дополнительных application
containers:

- `uv.lock` и editable `.venv` фиксируют Python 3.11 dependency graph, а
  `uv run --locked` импортирует `face_moment` из текущего `src/`;
- `compose.local.yaml` публикует только PostgreSQL/pgvector и MinIO на loopback
  через отдельную local bridge-сеть; release topology в `compose.yaml` не
  изменена;
- текущие незавершённые FT-009 gates используют `uv`, исторические receipts не
  переписаны;
- packaged proof остаётся `scripts/smoke-runtime.sh` с обязательным build;
- старые Face Moment application containers и восемь stale Python image tags
  удалены без удаления PostgreSQL/MinIO volumes.

Таким образом, неоднозначный bare-run больше не является штатным путём. Finding
закрыт; отдельные устаревшие/сломанные tests из finding 2 не входят в этот
repair.
