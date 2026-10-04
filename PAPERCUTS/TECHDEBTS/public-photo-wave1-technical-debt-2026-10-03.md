# Технический долг public photo — новая волна 1

Advisory-проверка: существенный технический долг в проверенной поверхности не подтверждён.

## Проверенная область

Только завершённый `TASK-120-T2-FT-013-W1` новой очереди FT-013–FT-016, camera/history subset FT-013-AC-001. Исторические задачи W1, остальные задачи новой очереди, backend, PAYMENS_TS, поиск и native accuracy не проверялись.

Фактическая поверхность: изменения `client/site-selfie.js:2,15,24,74,93`, `client/site.html:49`; новый `client/site-selfie-history.js:3–40`; `tests/client/test_site_selfie_history.mjs:4–30`, `tests/client/site_selfie_history.spec.mjs:11–163` и используемые portrait fixtures в `tests/client/fixtures/` (через проверенные browser evidence).

Проверены механизмы JPEG resize/no-upscale, append-only IndexedDB записи, обработка storage failure и сохранение текущего Blob отдельно от истории. Универсального storage слоя или дополнительного механизма управления историей не введено. Доказательств существенного повторного изменения, избыточной связности или подтверждённого риска регрессии в этой поверхности не обнаружено.

## Доказательства

- `.memory-bank/tasks/TASK-120-T2-FT-013-W1.task.json`: статус done, ограниченный outcome, нормативные ссылки и closure evidence.
- `.memory-bank/features/FT-013.md:31–36`: обязательства capture/history; `.memory-bank/contracts/public-photo-search-api.md:49`: владельцы browser/media требований.
- `.tasks/TASK-120-T2-FT-013-W1/TASK-120-T2-FT-013-W1-S-EXECUTE-final-report-code-01.md`: фактические изменения и пределы handoff.
- `.tasks/TASK-120-T2-FT-013-W1/claim-evidence.md`: RED/GREEN, quota/unavailable и current-only consumer; native proof явно отложен в соответствующую задачу.
- `.tasks/TASK-120-T2-FT-013-W1/TASK-120-T2-FT-013-W1-S-VERIFY-final-report-code-01.md`: независимый PASS, 83/83 unit и 4/4 browser journeys.
- `.tasks/TASK-120-T2-FT-013-W1/verifier-probe.json`: current/stored SHA-256, отсутствие upscale, asynchronous abort, сохранение истории после reload и отсутствие автоматической отправки.
- Текущий source diff указанных client файлов и исходники helper/tests прочитаны непосредственно.

## Подтверждённые находки

## Ограничения уверенности

Это краткая проверка сопровождения по исходникам и уже сохранённым доказательствам. Проверки не перезапускались. Результаты Chromium не доказывают совместимость всех браузеров; подтверждённых дефектов совместимости в доступных доказательствах нет. Native recognition, будущий search UI и PAYMENS_TS не относятся к TASK120 и не считаются отсутствующей реализацией или техническим долгом этой задачи. Рекомендаций по расширению scope нет.

Код, Memory Bank и workflow state не менялись; создан только этот отчёт.
