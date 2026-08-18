# Стратегический план миграции Face Moment на OpenCV 5

**Дата:** 2026-08-18  
**Статус:** dependency migration выполнена; container/runtime acceptance ещё не закрыта
**Целевой runtime:** точно закреплённая версия `opencv-python-headless` 5.x

## Цель

Перевести runtime проекта на OpenCV 5 и использовать его как единственную
поддерживаемую версию OpenCV.

OpenCV 5 — это библиотечный runtime, а не набор новых face-моделей. YuNet,
SFace, SCRFD и Buffalo M устанавливаются и проверяются отдельно.

## Текущее состояние

Проект использует OpenCV в следующих местах:

- декодирование и кодирование JPEG;
- resize изображений;
- YuNet через `cv2.FaceDetectorYN`;
- SFace через `cv2.FaceRecognizerSF`;
- тестовые и runtime smoke-проверки.

`InsightFace 0.7.3` используется только для pipeline SCRFD/Buffalo M. Его
версию не нужно менять одновременно с OpenCV 5. Совместимость проверяется в
рамках запуска существующего pipeline.

## Уже выполнено в исходниках

- В `pyproject.toml` закреплён `opencv-python-headless==5.0.0.93`.
- В `pyproject.toml` закреплён совместимый `numpy==2.2.6`: native package
  metadata OpenCV 5 требует NumPy 2 для Python 3.11.
- Добавлен regression smoke для обязательных image operations и наличия
  `FaceDetectorYN`/`FaceRecognizerSF`.
- Добавлен native SFace smoke, который при наличии model volume загружает
  YuNet/SFace, выполняет detection и, если найдено лицо, `alignCrop`/`feature`.

Полная container-проверка и runtime provisioning остаются отдельным этапом:
они не считаются выполненными по одному изменению dependency pin.

TASK-045 сейчас блокируется runtime-конфигурацией, допустимой pipeline revision
и active SPA. Четыре ONNX-файла уже присутствуют в workspace, но их наличие
само по себе не доказывает native admission, соответствие metadata или
готовность runtime. Само обновление OpenCV эти условия не создаёт
автоматически.

## План работ

### 1. Обновить runtime-зависимость

- закрепить конкретную проверенную версию OpenCV 5;
- сохранить Python 3.11, ONNX Runtime и InsightFace без изменений; NumPy
  поднять до совместимого exact pin, потому что wheel OpenCV 5 требует
  `numpy>=2` на Python 3.11;
- пересобрать Docker image;
- проверить импорт `cv2` и фактическую версию внутри контейнера.

### 2. Проверить существующий код

Прогнать текущие сценарии проекта для:

- `imdecode`, `imencode`, `resize`;
- `FaceDetectorYN.create`, `setInputSize`, `detect`;
- `FaceRecognizerSF.create`, `alignCrop`, `feature`;
- BGR-изображений, пустых результатов и размеров embedding.

Исправлять только фактически обнаруженные несовместимости. Архитектуру
pipeline не менять без необходимости.

### 3. Подтвердить model assets

Проверить и зафиксировать:

- `yunet.onnx`;
- `sface.onnx`;
- `scrfd.onnx`;
- `w600k_r50.onnx`.

### 4. Настроить admission и runtime

- заполнить обязательную конфигурацию моделей;
- создать допустимую pipeline revision на основе реальных файлов;
- подготовить одну active SPA штатным runtime-путём;
- запустить realtime и связанные сервисы;
- проверить model admission и health endpoints.

### 5. Завершить проверку

Выполнить применимые project-native проверки:

- Docker build;
- mypy;
- тесты;
- Memory Bank lint;
- свежий `/verify`;
- для T3-задач — `/red-verify`.

TASK-045 можно считать продолженным только после подтверждения реального
runtime с настоящими моделями и active SPA. Успешная сборка контейнера сама по
себе недостаточна.

## Критерии готовности

- проект собирается на OpenCV 5;
- все текущие применимые тесты и typecheck проходят;
- YuNet/SFace реально загружаются и обрабатывают изображения;
- SCRFD/Buffalo M либо работает, либо его отложенность явно оформлена;
- model metadata соответствует фактическим файлам;
- realtime runtime healthy;
- одна active SPA успешно обслуживается;
- verification evidence сохранена в проектных артефактах.

## Ограничения

- не менять продуктовую логику поиска;
- не обновлять InsightFace без отдельной причины;
- не создавать фиктивные модели или записи БД;
- не пересчитывать feature/task queue;
- не считать TASK-045 закрытым только по результату сборки.

## Оценка объёма

При отсутствии проблем совместимости — примерно 1–3 рабочих дня после
получения реальных моделей. Основная неопределённость находится в самих
модельных артефактах и запуске runtime, а не в количестве изменений Python-кода.

## Источники

- [OpenCV 5 DNN face detection and recognition](https://docs.opencv.org/5.0/tutorials/dnn/dnn_face/dnn_face.html)
- [OpenCV 5 face API reference](https://docs.opencv.org/5.0/main_modules/objdetect_dnn_face.html)
- [opencv-python-headless на PyPI](https://pypi.org/project/opencv-python-headless/)
- [InsightFace 0.7.3 на PyPI](https://pypi.org/project/insightface/0.7.3/)
