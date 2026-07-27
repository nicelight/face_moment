# Face Moment: SpaPromoClient и локальная подготовка reference series

Обновлено: 2026-07-27

## 0. Статус документа

Этот документ фиксирует обсуждённые нюансы и явно принятые оператором решения
о `SpaPromoClient`, подключении камеры и датчика, локальной обработке
`reference series`, client/server boundary и отношении проекта к media content.

Это не implementation plan и не разрешение автоматически менять остальные
файлы проекта. До отдельной команды оператора документ служит самостоятельным
decision/context handoff. При последующем согласовании с Memory Bank явные
решения из этого документа имеют приоритет над более ранними противоречащими
формулировками.

## 1. Роль SpaPromoClient

`SpaPromoClient` работает на клиентской машине у Promo display и отвечает за:

- постоянное получение video stream выбранной камеры;
- короткий локальный ring buffer;
- приём события от passage sensor;
- формирование pre/post-trigger `reference series`;
- локальное обнаружение всех видимых лиц в `reference series`;
- подготовку face crops и metadata для server request;
- отправку bounded realtime request;
- управление локальными display states, рекламой, Promo и recovery;
- диагностические timestamps клиентских этапов.

Client-side обработка не создаёт embeddings и не выполняет поиск по
коммерческим фотографиям. Embeddings, exact search, candidate pools, teaser
selection и формирование `N` остаются на сервере.

Полное локальное распознавание, включая создание embeddings и поиск, не входит
в текущее решение. Возможность такого переноса рассматривается только после
benchmark на реальной client machine, выбранной камере и данных pilot.

## 2. Камера и configuration UI

### 2.1 Принятое направление

Точная модель камеры пока не выбрана. Наиболее вероятный класс устройства —
обычная USB webcam, доступная Chromium как video input.

Выбор конкретной модели остаётся результатом проверки реальной площадки,
дистанции 3–5 метров, освещения, motion blur, размера лица, pose и exposure.
Отсутствие выбранной модели сейчас не должно жёстко связывать client design с
одним vendor или USB port.

### 2.2 Выбор камеры

В configuration UI клиент должен:

- получить список всех доступных browser-visible video inputs;
- показать понятные названия устройств после получения browser permission;
- позволить оператору явно выбрать используемую камеру;
- показать preview выбранной камеры до подтверждения;
- запомнить выбранное устройство настолько, насколько browser сохраняет его
  device identity;
- уметь повторно получить список устройств по запросу оператора и при изменении
  набора подключённых устройств.

Client не должен молча переключаться на случайную другую камеру, если ранее
выбранное устройство исчезло.

### 2.3 Переподключение и смена USB port

Переподключение той же камеры, в том числе в другой USB port, не должно
оставлять систему в необъяснимо сломанном состоянии.

После disconnect/reconnect клиент повторно обнаруживает доступные video inputs.
Если browser продолжает узнавать ранее выбранную камеру, client может
восстановить её использование. Если device identity изменилась или нужная
камера больше не найдена, configuration UI показывает актуальный список и
просит оператора заново выбрать и проверить preview.

Пока usable camera не выбрана, display сохраняет локальную рекламу и не
запускает capture/search attempt.

## 3. Passage sensor и тестовое срабатывание

### 3.1 Принятое направление

Passage sensor предполагается выполнить как автономное устройство на ESP32.
ESP32 находится в той же локальной сети, что и client machine.

ESP32 сообщает только о факте срабатывания датчика. Camera stream постоянно
ведётся клиентом; sensor event не включает камеру и не открывает отдельный
затвор, а отмечает `t=0` в уже существующем stream/ring buffer.

### 3.2 Test trigger

Configuration UI содержит явно обозначенную кнопку имитации срабатывания
датчика.

Test trigger не является отдельным упрощённым demo path. Он входит в тот же
локальный trigger-acceptance path, что и событие ESP32:

- формирует новую `reference series`;
- запускает тот же local detector;
- создаёт тот же request payload;
- соблюдает те же capture/search/cooldown locks;
- не обходит защиту от overlapping и stale attempts.

В metadata должен быть различим источник trigger, чтобы физическое и тестовое
срабатывания можно было отличить при диагностике.

### 3.3 Пока не выбранный transport

Конкретный ESP32-to-client protocol пока не утверждён. Обсуждался постоянный
client-initiated WebSocket connection к настроенному LAN endpoint ESP32 с
reconnect и health state, но это остаётся предложением, а не принятым решением.

Также пока не решены:

- обнаружение или ручная настройка ESP32 address;
- pairing и идентификация нужного sensor;
- формат trigger event;
- reconnect/backoff и отображение sensor health;
- поведение при временном исчезновении ESP32 из сети.

## 4. Reference series и local detector

### 4.1 Обычный Promo flow

В обычном рабочем Promo flow полные тяжёлые кадры `reference series` не
отправляются на сервер.

Последовательность выглядит так:

```text
camera video stream
→ local ring buffer
→ sensor/test trigger
→ pre/post-trigger reference series
→ client-side face proposal detection
→ crops всех найденных face occurrences + metadata
→ server-side validation, ranking и selection
→ server-side native alignment, embeddings и exact search
→ Promo result
```

Полные reference frames остаются на client machine как минимум на время
обработки текущей попытки. Текущий pilot не требует отправлять их на сервер,
чтобы доказывать или размечать лица, полностью пропущенные local detector.

### 4.2 Local detector только предлагает лица

Утверждён вариант, в котором local detector является proposal detector.

Он выполняет:

- поиск face occurrences во всех кадрах сформированной `reference series`;
- подготовку отдельного crop для каждого найденного occurrence;
- сбор относящейся к occurrence и исходному кадру metadata.

Он не выполняет:

- face embedding;
- face recognition или поиск;
- authoritative query-quality gating;
- ranking найденных лиц;
- выбор локального top-5;
- tracking одного человека между кадрами;
- identity clustering;
- cross-frame person deduplication;
- объединение нескольких detections в одну person identity.

Термин «найденное лицо» в client contract означает только detected face
occurrence. Он не означает распознанную person identity. Единственный `top-5`
в текущем flow формируется позже на сервере, после получения client proposals.

### 4.3 Отправляются все найденные лица

Client-side не ищет, не формирует и не отправляет собственный `top-5`.
Он не ранжирует detections и не отбрасывает их до отправки по quality rule.
В один server request входят отдельные crops и metadata всех без исключения
face occurrences, которые local detector вернул для текущей
`reference series`.

Один физический человек может появиться:

- в нескольких кадрах;
- несколько раз в request;
- во всех найденных occurrences.

Это допустимо. Client не пытается доказать, какие detections принадлежат одному
человеку.

Фраза «отправить все найденные лица» задаёт semantic behavior и не отменяет
обычные технические ограничения на общий размер HTTP request, число decoded
pixels и валидацию входа. Такие ограничения не должны незаметно превращаться в
client-side quality ranking или скрытый выбор пяти лиц. Если request со всеми
proposals не помещается в принятые hard bounds, попытка получает явный
non-success outcome; client не выбирает и не отправляет произвольное подмножество.

### 4.4 Server-side authority

Сервер получает proposed crops и metadata, после чего:

- валидирует request и каждый crop;
- применяет server-authoritative quality calculation;
- ранжирует received proposals;
- выбирает не более пяти detections для дальнейшей обработки согласно текущему
  best-effort group contract;
- повторяет native detector/alignment path активного serving pipeline внутри
  выбранного crop, когда это требуется pipeline;
- создаёт embeddings;
- выполняет exact scoped search;
- формирует candidate pools, четыре teasers и полный `N`.

Таким образом, client proposal detector не становится частью immutable
commercial embedding compatibility. SFace/YuNet и Buffalo M/SCRFD сохраняют
собственные native preprocessing/alignment paths на сервере.

Двойная detection — сначала proposal detection на клиенте, затем
pipeline-native validation/alignment на сервере — является осознанным
компромиссом. Он уменьшает network payload, но не связывает client release
жёстко с active serving pipeline.

### 4.5 Нулевой результат local detector

Если local detector не нашёл ни одного лица, попытка не должна исчезать из
диагностики.

Client всё равно отправляет metadata-only request с тем же `attempt_id` и
client-side stage timings, но без crops. Сервер создаёт core Attempt и
возвращает typed non-success domain outcome. Точное машинное имя outcome
остаётся частью будущего API contract.

Этот путь отличается от полной недоступности сервера. При client-only network
failure durable server Attempt по-прежнему может отсутствовать.

## 5. Crops и metadata

### 5.1 Crop не является готовым embedding input

Client crop — это переносимый proposal region, а не доказательство валидного
лица и не обязательно окончательно aligned image для recognizer.

Crop должен оставлять серверу достаточно context для native detector и
alignment. Точные padding, minimum dimensions, aspect handling, image encoding,
quality и orientation ещё не утверждены и должны проверяться benchmark-ом.

Слишком тесный crop может отрезать landmarks или ухудшить повторную detection.
Слишком широкий crop увеличивает payload и может снова содержать несколько лиц.
Этот баланс остаётся отдельным техническим решением.

### 5.2 Metadata

Принято, что вместе с crops передаётся metadata, достаточная для корреляции,
диагностики и server-side processing.

Обсуждавшиеся, но ещё не зафиксированные как окончательная schema поля:

- `attempt_id/correlation_id`;
- источник trigger: ESP32 или test UI;
- client release и local detector version;
- camera/config identity;
- reference-frame index и local timestamp;
- исходные frame dimensions;
- proposal bbox и crop dimensions;
- detection confidence;
- доступные local quality observations;
- client-side stage timings;
- crop encoding и byte size.

Конкретные имена, обязательность полей и serialization format пока не выбраны.

## 6. Stage timings и performance

### 6.1 Разделение этапов

Принято, что локальная подготовка не должна сливаться в один общий
необъяснимый интервал.

На client side отдельно наблюдаются:

- формирование `reference series`;
- local detection;
- crop extraction/encoding;
- начало и завершение upload/request;
- получение response;
- Promo render и полная видимость QR.

Поскольку client-side ranking отменён, ranking/selection timing относится к
server-side stage, а не к client-side processing.

На debug page минимально достаточно показать client-local markers:

- начало обработки готовой `reference series`;
- начало отправки request на сервер;
- получение server response.

Полезные дополнительные durations, включая local detection, crop encoding и
полную видимость QR, могут показываться там же, но не требуют distributed
tracing или синхронизации client/server clocks.

На server side отдельно наблюдаются:

- request validation/admission;
- proposal quality calculation;
- ranking и selection до пяти detections;
- pipeline-native detection/alignment;
- embedding inference;
- vector search;
- candidate/result assembly.

Точный формат wall-clock timestamps и monotonic elapsed durations остаётся
частью contract design. Межмашинное вычитание несинхронизированных часов не
должно использоваться для acceptance latency.

### 6.2 Acceptance anchor

В проекте уже используется `reference_series_ready_at` как начало основного
`<10 s` интервала. Принято сохранить его KISS-определение: это client-local
момент завершения capture window, когда `reference series` сформирована и
начинается local processing.

Основная acceptance latency считается на одном client monotonic clock:

```text
qr_fully_visible_elapsed_ms - reference_series_ready_elapsed_ms
```

В `<10 s` входят local detection, crop extraction/encoding, request upload,
server processing, получение response и Promo/QR render. Межмашинное вычитание
wall-clock timestamps, clock synchronization и отдельный distributed tracing
для этой метрики не требуются.

## 7. Media content и diagnostic policy

### 7.1 Принятое отношение к media

В этом проекте media content не получает специальный protected status только
потому, что содержит изображение или face crop.

Reference images, normalized images, face crops и другое capture-derived media
не считаются protected artifacts. Они могут:

- попадать в logs;
- храниться в обычном cache;
- передаваться по публичной ссылке или публичному response;
- показываться без developer-only media authorization;
- храниться вместе с обычными diagnostic records.

Само наличие лица в crop не делает этот crop чувствительными данными в
принятой для проекта классификации.

Это решение отменяет прежние утверждения о том, что images/crops обязательно:

- доступны только application developer;
- должны храниться отдельно от log records;
- открываются только по authorized artifact links;
- требуют `no-store` исключительно из-за media content;
- не могут быть публично отданы или закэшированы.

### 7.2 Что это решение не отменяет автоматически

Решение о media content не превращает в публичные:

- `spa_client_token` и другие credentials;
- authentication headers;
- cookies и session tokens;
- PostgreSQL, MinIO или Docker API;
- participant names, если они существуют только в role-scoped annotations;
- serving settings mutation и административные actions.

Коммерческие `Photo` originals, paid-delivery semantics, personalized Promo
session authorization и hard-purge behavior являются отдельными продуктовыми
границами. Текущий разговор не зафиксировал, что они должны быть изменены
только вследствие публичности capture-derived crops.

### 7.3 Logging и caching не должны ломать critical flow

Разрешение логировать или кэшировать media означает отсутствие запрета по
классификации данных, а не обязательную запись каждого crop во все logs.

Logging, diagnostic ingestion и caching по-прежнему не должны:

- блокировать capture/search/Promo/QR;
- создавать unbounded synchronous I/O на critical path;
- скрывать core Attempt при сбое detailed evidence;
- логировать credentials вместе с разрешённым media.

Конкретный формат хранения выбирается по простоте, стоимости и полезности
диагностики, а не ради отдельного security contour для images/crops.

Media classification не отменяет существующий retention lifecycle: если
capture-derived media сохраняется как ordinary diagnostic evidence, на него
распространяется обычный 90-day cutoff; вручную promoted curated subset может
жить до явного удаления. Это не требует отдельной media-retention системы.
Release cache ONNX model и diagnostic media cache являются разными concerns.

### 7.4 Normal Promo flow и diagnostic mode

Уточнение «на сервер отправляются только crops и metadata» относится к обычному
рабочему Promo flow.

Текущий pilot не обязан доказывать, что local detector пропустил лицо, и не
вводит ради этого отдельный diagnostic/acceptance frame-upload mode. Полные или
downscaled reference frames не входят в обязательный request, acceptance
evidence или Calibration dataset. Если такая диагностика позже получит
отдельную практическую ценность, она потребует нового явного решения, но не
должна заранее усложнять текущий client/server flow.

### 7.5 Следствие для нормативных спецификаций

Решение о media classification должно быть согласовано во всём затронутом
нормативном контуре, а не только в одном feature:

- PRD, stable requirements и RTM;
- product/epic/feature decomposition;
- glossary и invariants;
- architecture, boundary и lifecycle contracts;
- diagnostics, logging, retention, testing и acceptance rules.

Reconciliation должна убрать обязательный protected status и обязательную
developer-only media authorization для capture-derived images/crops. Она не
должна автоматически делать публичными credentials, infrastructure endpoints,
commercial Photo originals, personalized Promo sessions, participant names или
administrative actions. Разрешение media logging/caching/public delivery также
не создаёт обязательный public endpoint, cache layer или запись каждого crop.

## 8. Client runtime route

Под «единственным client route» понимается место, где выполняются camera access,
local detector и ESP32 integration.

### 8.1 Browser-native route

В browser-native варианте:

- Chromium получает camera stream через browser media APIs;
- configuration UI выбирает camera video input;
- local proposal detector выполняется в browser runtime;
- ESP32 доступен через browser-compatible LAN protocol;
- один web bundle управляет capture, display и recovery;
- отдельного native daemon нет.

Преимущество — меньше процессов и единый client bundle. Необходимо проверить
реальную производительность detector, стабильность camera access, browser
permissions, model loading и LAN integration.

### 8.1.1 Подтверждённое browser-runtime направление

Для browser-native feasibility подтверждены следующие технические свойства:

- `ONNX Runtime Web` выполняет CPU inference через WebAssembly; для CPU
  предпочтительны небольшие модели и `uint8` quantization;
- WASM multithreading работает только при `crossOriginIsolated`; client app
  shell должен корректно выставлять `COOP`/`COEP` headers и проверять
  `self.crossOriginIsolated`;
- proxy/Web Worker сохраняет отзывчивость UI, но сам по себе не ускоряет
  inference; производительность дают подходящая модель, WASM SIMD и внутренние
  WASM threads;
- YuNet является текущим compact proposal-detector candidate: OpenCV Zoo
  публикует quantized-вариант и указывает примерно 10×10–300×300 px как
  training-derived диапазон размеров лиц;
- точный YuNet artifact, checksum, format и byte size фиксируются release
  manifest и benchmark, а не становятся вечным product contract;
- для небольшого release-versioned model artifact достаточно Cache API:
  модель скачивается при отсутствии нужной release version, а новая in-memory
  `InferenceSession` создаётся после запуска или reload client;
- generic storage abstraction поверх Cache API/OPFS/IndexedDB не требуется,
  пока один model artifact не докажет обратное.

Источники:

- [ONNX Runtime Web Performance Diagnosis](https://onnxruntime.ai/docs/tutorials/web/performance-diagnosis.html);
- [ONNX Runtime Web model caching](https://onnxruntime.ai/docs/tutorials/web/large-models.html);
- [OpenCV Zoo YuNet](https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/README.md).

### 8.2 Narrow local bridge

В bridge-варианте:

- рядом с Chromium работает один небольшой local process;
- он может владеть native camera/device access и local ML runtime;
- web UI получает device list, preview, trigger и proposal results через узкий
  local contract;
- тот же client bundle продолжает управлять display UX.

Преимущество — доступ к native libraries и hardware protocols. Цена — ещё один
process, packaging/update/restart contract и дополнительная operational
граница.

### 8.3 Текущий статус route

Ни browser-native route, ни narrow local bridge пока не утверждены оператором.
Предыдущая рекомендация browser-native не является принятым решением.

Не следует одновременно строить обе реализации или generic device-plugin
framework до появления подтверждённой необходимости. Сначала выбирается один
pilot route по результатам проверки client hardware и local detector.
Подтверждённые свойства ONNX Runtime Web/YuNet уменьшают неопределённость
browser-native candidate, но не заменяют benchmark на реальной client machine,
выбранной camera geometry и representative frames.

## 9. Нюансы диагностики и Calibration

Перенос proposal detection на client создаёт отдельный источник ошибок:

- лицо может быть пропущено local detector и вообще не попасть на сервер;
- crop может обрезать context, нужный native pipeline;
- один человек может создать много proposal crops;
- client detector version может изменить population server-side detections;
- latency может переместиться с network/server на client processing.

Поэтому диагностика должна уметь различать:

- `no_face_proposals` на client;
- proposals, отклонённые request validation;
- proposals, не прошедшие server quality gates;
- proposals, не выбранные server ranking в top-5;
- выбранные detections без threshold-valid search result;
- successful detections, повлиявшие на teasers и `N`.

Для воспроизводимости важна версия local proposal detector наряду с active
server pipeline revision. Однако local detector version не становится
embedding compatibility identity.

Outcome `no_face_proposals` показывает, что client detector не вернул
occurrences, но текущий pilot не обязан доказывать, присутствовало ли в
reference frames фактически пропущенное лицо. Отдельная разметка local-detector
misses и diagnostic frame mode не входят в scope.

## 10. Failure и recovery semantics

- Camera unavailable: local advertising остаётся активной, capture не
  начинается, configuration UI показывает recoverable camera-selection state.
- ESP32 unavailable: display продолжает local advertising; test trigger может
  использоваться для проверки остального client path.
- No local proposals: metadata-only server request сохраняет Attempt и
  non-success outcome.
- Server unavailable: client возвращается/остаётся в advertising, показывает
  согласованное короткое сообщение о неудачной связи и не сохраняет stale
  personalized result.
- Timeout или stale response: retry требует новой `reference series`, старые
  crops не переигрываются как новая попытка.
- Browser/client restart: in-memory frames, crops и personalized result могут
  быть отброшены; realtime work не становится durable queue.
- Новый sensor/test trigger во время capture/search или successful cooldown
  игнорируется по общему client state contract.

## 11. Принятые решения

На 2026-07-27 явно приняты:

1. Вероятный pilot camera class — USB webcam; точная модель выбирается после
   site validation.
2. Configuration UI показывает доступные video inputs, preview и явный выбор
   камеры и восстанавливается после disconnect/reconnect или смены USB port.
3. Passage sensor предполагается автономным ESP32 в той же LAN, что и client.
4. Configuration UI имеет test trigger, использующий тот же processing path.
5. `Reference series` обрабатывается на client machine до server request.
6. Local detector является только proposal detector.
7. Client не ранжирует и не выбирает top-5, а отправляет crops и metadata всех
   найденных face occurrences.
8. Tracking, clustering и cross-frame person deduplication на client
   отсутствуют.
9. Server выполняет authoritative quality calculation, ranking, выбор до пяти
   detections, native pipeline alignment, embeddings и exact search.
10. В обычном Promo flow полные reference frames не отправляются; отправляются
    face crops и metadata.
11. При нуле найденных лиц отправляется metadata-only request, чтобы
    server-admitted Attempt не исчезал из диагностики.
12. Client и server processing stages получают отдельные timings; ranking
    относится к server side.
13. Embeddings и поиск пока остаются на сервере; полное локальное распознавание
    рассматривается только после benchmark.
14. Capture-derived images/crops не считаются protected artifacts и могут
    логироваться, кэшироваться и публично отдаваться.
15. Разрешение публичного media не отменяет защиту credentials, tokens,
    infrastructure ports и role-scoped non-media administration.
16. `reference_series_ready_at` остаётся моментом завершения capture window и
    начала local processing; весь local detection/upload входит в основной
    `<10 s` interval.
17. Acceptance latency считается на одном client monotonic clock без
    межмашинной синхронизации; debug page показывает как минимум начало
    обработки reference series, начало server request и получение response.
18. Pilot не обязан доказывать local-detector misses и не вводит обязательный
    diagnostic frame-upload mode.
19. Persisted ordinary capture-derived diagnostic media сохраняет текущий
    90-day cutoff; отдельный media-retention lifecycle не вводится.

## 12. Не принятые решения

Пока не выбраны:

- browser-native или narrow local bridge route;
- ESP32-to-client transport;
- конкретная camera и конкретный sensor hardware;
- client proposal detector, runtime, model format и update mechanism;
- crop padding, encoding, dimensions и image quality;
- окончательная request/response schema;
- exact request byte/pixel limits;
- необходимость будущего переноса embeddings/search на client.
