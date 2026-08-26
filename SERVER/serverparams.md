# Параметры тестового сервера Face Moment

Последнее обновление: 2026-08-26

Этот файл фиксирует только параметры, подтверждённые командами на тестовом
сервере. Параметры сети и свободные ресурсы являются снимком состояния и могут
измениться.

## Назначение

- Роль машины: центральный тестовый CPU-only сервер Face Moment.
- Этап: первоначальная подготовка к one-СПА pilot.
- Способ текущего удалённого доступа: RustDesk.
- VPN и SSH-доступ через VPN: отложены до отдельного этапа.

## ОС и платформа

| Параметр | Значение |
|---|---|
| Hostname | `face-pc` |
| Тип устройства | laptop |
| Дистрибутив | Kubuntu 26.04.1 LTS с KDE Plasma; `hostnamectl` сообщает `Ubuntu 26.04.1 LTS` |
| Kernel | `Linux 7.0.0-30-generic` |
| Архитектура | `x86-64` |
| Firmware | `S1-144HZ01[08/01/2025]` |
| Firmware date | `2025-08-01` |
| System locale | `ru_RU.UTF-8` |
| Раскладки X11 | `us,ru`, переключение `Alt+Shift` |
| Часовой пояс | `Asia/Novosibirsk` (`UTC+07:00`) — соответствие физическому расположению ещё нужно подтвердить |
| Синхронизация времени | NTP active, system clock synchronized, RTC в UTC |

После package update ОС не требует перезагрузки. `systemctl --failed` не
показывает failed units.

## Процессор

| Параметр | Значение |
|---|---|
| Модель | Intel Core i7-8850H @ 2.60 GHz |
| Сокеты / ядра / потоки | 1 / 6 / 12 |
| Частоты | 800 MHz – 4.30 GHz |
| L3 cache | 9 MiB |
| Нужные CPU-инструкции | AVX и AVX2 присутствуют |
| Виртуализация | Intel VT-x |
| NUMA | 1 node |

Ядро сообщает активные mitigations для большинства известных уязвимостей этого
поколения CPU. Для `Gather data sampling` показан статус `Vulnerable`. Пакет
`intel-microcode` установлен в актуальной доступной версии
`3.20260210.1ubuntu2`.

Для первоначального one-СПА теста процессор подходит. Он слабее целевого
ориентира из `IDEA_OS.md` для нагрузки 10–15 СПА, поэтому CPU affinity и итоговая
пригодность должны определяться только после benchmark на рабочей модели.

## Оперативная память

| Параметр | Значение на момент проверки |
|---|---|
| RAM всего | 15 GiB |
| RAM используется | 3.9 GiB |
| RAM доступно | 11 GiB |
| Swap | 511 MiB, не использовался |

15 GiB достаточно для первоначального ограниченного теста, но это меньше
ориентира 64 GiB из серверной концепции. Размер swap требует отдельного решения
после проверки диска и реального потребления памяти.

## Накопитель

| Устройство | Разметка | Файловая система | Использование |
|---|---|---|---|
| `/dev/nvme0n1`, 238.5 GiB | GPT/UEFI | — | системный NVMe |
| `/dev/nvme0n1p1`, 300 MiB | EFI System Partition | FAT | `/boot/efi`, занято 8.1 MiB |
| `/dev/nvme0n1p2`, 238.2 GiB | root | ext4 | `/`, 234 GiB доступного объёма FS, занято 16 GiB, свободно 206 GiB |

NVMe model: `SBSSD256-STE14-M2P3`, firmware `APF1M3R1`, NVMe 1.3. Проверка
`smartctl -x` пройдена:

- overall health: `PASSED`;
- critical warning: `0x00`;
- available spare: 100%;
- percentage used: 0%;
- media/data integrity errors: 0;
- error log entries: 0;
- power-on hours: 3;
- power cycles: 5;
- unsafe shutdowns: 3;
- composite temperature: около 38 °C;
- warning/critical temperature time: 0.

Три unsafe shutdown при пяти включениях нужно наблюдать, но ошибок носителя нет.
Свободного пространства достаточно для установки и ограниченного pilot, но оно
не зафиксировано как достаточное для целевого 30-дневного хранения фотографий.

## Температуры на момент проверки

| Компонент | Температура / наблюдение |
|---|---|
| CPU package | 58 °C |
| CPU cores | 52–58 °C |
| Wi-Fi sensor | 55 °C |
| PCH Cannon Lake | 69 °C |
| NVMe composite | около 38 °C |
| NVMe sensor 1 | около 57 °C |

Критического перегрева во время проверки нет. Показание батареи `756.72 W`,
ACPI temperature `0 °C` и ошибки чтения NVMe `temp2_min/temp2_max` выглядят как
некорректные или неподдерживаемые sensor fields, а не как реальные измерения.

## Сеть

| Интерфейс | Состояние | Адрес |
|---|---|---|
| `wlp4s0` | UP | DHCP IPv4 `192.168.3.57/24`, также назначены IPv6-адреса |
| `enp3s0` | DOWN | адрес не назначен |
| `docker0` | DOWN без запущенных постоянных контейнеров | `172.17.0.1/16` |

- Default route: `192.168.3.1` через Wi-Fi `wlp4s0`.
- Текущий IPv4 получен по DHCP и не считается постоянным адресом сервера.
- UFW установлен, но неактивен.
- Для эксплуатации предпочтителен проводной Ethernet; переключение сети пока
  не выполнялось.
- Входящие соединения из интернета для центрального сервера не планируются.

## Пользователи и доступ

### `face`

- UID/GID: `1000/1000`.
- Первоначальный bootstrap-user с `sudo`.
- Не входит в группу `docker`.
- Текущая графическая KDE-сессия и компоненты RustDesk используют
  `/home/face`.
- Пользователь пока сохраняется, чтобы не потерять единственный проверенный
  удалённый доступ.

### `facemoment`

- UID/GID: `1001/1001`.
- Группы: `facemoment`, `sudo`, `users`, `docker`.
- Домашний каталог: `/home/facemoment`.
- Shell: `/bin/bash`.
- Пароль задан; `sudo -v` успешно проверен.
- Доступ к Docker socket без `sudo` успешно проверен.

### `display`

- Ещё не создан.
- В дальнейшем должен быть непривилегированным пользователем KDE/Chromium без
  `sudo`, SSH и группы `docker`.

## Docker

| Компонент | Состояние |
|---|---|
| Docker Engine | `29.7.2` |
| Docker Compose | `v5.5.0` |
| `docker.service` | active, enabled |
| Docker group | GID `975` |
| Проверка контейнера | `docker run --rm hello-world` успешно выполнена от `facemoment` |

Установлен Docker Engine, а не Docker Desktop. Постоянный Compose stack проекта
ещё не развёрнут.

## Удалённый доступ и host-службы

| Компонент | Состояние |
|---|---|
| RustDesk system service | active, enabled |
| RustDesk GUI/session | работает в графической сессии пользователя `face` |
| AnyDesk | active, enabled; в журнале текущей загрузки есть stack trace одного процесса, использование ещё нужно уточнить |
| OpenSSH server (`sshd`) | не установлен или отсутствует в `PATH` |
| Chromium | не установлен или отсутствует в `PATH` |
| Git | `/usr/bin/git` |
| `smartctl` | `/usr/sbin/smartctl` |
| `sensors` | `/usr/bin/sensors` |

До проверки восстановления RustDesk после logout/reboot запрещено удалять или
переименовывать `face`, менять SDDM autologin и выполнять удалённую перезагрузку
без резервного способа доступа.

## Наблюдения журнала текущей загрузки

- `systemctl --failed`: `0 loaded units listed`.
- В kernel journal массово повторяется корректируемый PCIe Physical Layer
  `RxErr` для root port `0000:00:1d.6`. Downstream device `0000:04:00.0` —
  Intel Dual Band Wireless-AC 7265 `[8086:095a]`, использующий driver `iwlwifi`.
  Загружена firmware `29.9ef079ed.0 7265D-29.ucode`. Это текущий рабочий
  Wi-Fi-интерфейс сервера. NVMe находится на другой ветке PCIe и по SMART
  исправен.
- Chrony синхронизирован с `ntp-nts-1.ps6.canonical.com`, stratum 3, leap status
  `Normal`, system offset около 8 ms. Четыре остальных NTS source сейчас
  недоступны; прежние certificate failures не блокируют текущую синхронизацию.
- В журнале присутствует stack trace `/usr/bin/anydesk`. RustDesk при этом
  остаётся active/enabled, AnyDesk также active/enabled, а failed systemd units
  отсутствуют.
- Во время диагностики произошла незапланированная перезагрузка. После неё
  машина автоматически вернулась в графическую сессию `face`, а удалённый
  доступ восстановился. Причина и штатность завершения предыдущей загрузки ещё
  не определены; read-only `ethtool -i` не считается доказанной причиной.
