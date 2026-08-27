# Параметры тестового сервера Face Moment

Последнее обновление: 2026-08-27

Этот файл содержит два типа сведений:

1. фактически подтверждённые параметры центрального тестового сервера Face Moment;
2. фактические параметры публичного VPS и утверждённую целевую сетевую
   инфраструктуру.

Параметры центрального сервера, сети и свободных ресурсов являются снимком
состояния и могут измениться. Ещё не проверенные части интеграции VPS и
центрального сервера явно отмечены как планируемые.

## Назначение

- Центральная машина: CPU-only сервер Face Moment для one-СПА pilot.
- Центральная машина находится за CGNAT и не должна принимать прямые входящие
  соединения из интернета.
- Публичная точка входа проекта: отдельный VPS с белым IPv4.
- VPS и центральный Kubuntu-сервер связываются постоянным
  `IKEv2/IPsec`-туннелем через `strongSwan`.
- Центральный сервер сам инициирует туннель наружу; прохождение CGNAT выполняется
  через IPsec NAT-T.
- Обычные Windows-клиенты Face Moment **не подключаются к VPN**. Они работают
  через обычный HTTPS к публичному VPS.
- VPS принимает публичный HTTPS через Caddy и проксирует разрешённый трафик к
  центральному серверу через IPsec.
- PostgreSQL, MinIO, Docker API, служебные порты и SSH центрального сервера
  публично не публикуются.
- Текущий резервный удалённый доступ к центральной машине: RustDesk.
- Отдельный административный IKEv2-доступ для операторов/разработчиков может
  быть добавлен позднее, но не является частью рабочего клиентского пути
  Face Moment.

## ОС и платформа центрального сервера

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
| Часовой пояс | `Asia/Novosibirsk` (`UTC+07:00`), соответствует физическому расположению сервера |
| Синхронизация времени | NTP active, system clock synchronized, RTC в UTC |

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

| Параметр | Значение |
|---|---|
| RAM всего | 15 GiB |
| Swap | 4 GiB, файл `/swapfile` |

15 GiB достаточно для первоначального ограниченного теста, но это меньше
ориентира 64 GiB из серверной концепции.

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

## Сеть центрального сервера

| Интерфейс | Состояние | Адрес |
|---|---|---|
| `wlp4s0` | UP | DHCP IPv4 `192.168.3.57/24`, также назначены IPv6-адреса |
| `enp3s0` | DOWN | адрес не назначен |
| `docker0` | DOWN без запущенных постоянных контейнеров | `172.17.0.1/16` |

- Default route: `192.168.3.1` через Wi-Fi `wlp4s0`.
- Текущий IPv4 получен по DHCP и не считается постоянным адресом сервера.
- Центральный сервер находится за NAT/CGNAT; белый IPv4 ему не требуется.
- UFW установлен, но неактивен.
- Для эксплуатации предпочтителен проводной Ethernet; переключение сети пока
  не выполнялось.
- Прямые входящие соединения из интернета для центрального сервера не
  планируются.
- После развёртывания VPN центральный сервер должен сам поддерживать постоянный
  исходящий IKEv2/IPsec-сеанс с VPS.

## Целевая внешняя инфраструктура: публичный VPS

Этот раздел фиксирует проверенные параметры развёрнутого VPS и утверждённую
архитектуру его интеграции с центральным сервером.

### Роль VPS

VPS является единственной публично адресуемой инфраструктурной машиной
Face Moment и выполняет четыре функции:

1. публичная HTTPS-точка входа;
2. reverse proxy до центрального сервера;
3. IKEv2/IPsec-концентратор для постоянного backhaul до Kubuntu-сервера за
   CGNAT;
4. контролируемая административная точка доступа к внутренней инфраструктуре.

VPS не должен хранить основную базу фотографий, PostgreSQL или MinIO и не
является вычислительным сервером распознавания лиц.

### Фактическая платформа VPS

| Параметр | Значение |
|---|---|
| Hostname | `almalinux9` |
| ОС | AlmaLinux 9.8 (Olive Jaguar) |
| Kernel | `Linux 5.14.0-687.41.1.el9_8.x86_64` |
| Виртуализация | VMware |
| CPU | 2 vCPU, AMD EPYC 9654 |
| RAM | 1.7 GiB |
| Swap | 190 MiB |
| Диск | 20 GiB, root `ext4` |
| Сетевой адрес | статический публичный IPv4 `46.8.200.99` |
| Часовой пояс | `UTC`, NTP synchronized |
| SELinux | Enforcing |
| VPN implementation | `strongSwan 6.0.6`, `charon-systemd` + `swanctl` |
| VPN protocol | `IKEv2/IPsec` |
| NAT traversal | IPsec NAT-T |
| Tunnel interface | XFRM `ipsec0`, VPS `10.77.0.1/30`, MTU `1400` |
| Tunnel status | VPS responder готов; соединение с Kubuntu ещё не установлено |
| Публичный reverse proxy | `Caddy`, ещё не установлен |
| Host firewall | `firewalld` с nftables backend |
| Публичный HTTPS | TCP `443` |
| IKE | UDP `500` |
| IPsec NAT-T | UDP `4500` |
| SSH VPS | `root`, key-based и password authentication; локальный alias `ssh igornskprod` |
| Docker на VPS | не требуется для базовой схемы |

Провайдер, датацентр и сетевой лимит VPS пока не зафиксированы.

### VPN/backhaul

Основной постоянный туннель:

```text
VPS / AlmaLinux / public IPv4
        │
        │ IKEv2/IPsec
        │ NAT-T UDP/4500
        │
        ▼
Internet / CGNAT
        │
        ▼
Kubuntu central server
```

Ключевые свойства:

- инициатором соединения является центральный Kubuntu-сервер;
- VPS имеет стабильный публичный IP и принимает IKEv2;
- CGNAT на стороне центрального сервера не требует port forwarding;
- при наличии NAT полезный IPsec-трафик инкапсулируется в UDP/4500;
- `strongSwan` работает на обеих Linux-машинах;
- основной data plane IPsec обрабатывается ядром Linux;
- tunnel должен автоматически подниматься после перезагрузки и
  восстанавливаться после временного разрыва мобильного/ISP-соединения;
- NAT keepalive и DPD должны быть настроены так, чтобы быстро обнаруживать
  потерю внешнего соединения и восстанавливать tunnel;
- MTU/MSS должны быть проверены на реальном канале, чтобы исключить black-hole
  и зависание крупных HTTPS multipart upload.

Служебная адресация туннеля:

```text
VPS:             10.77.0.1
Kubuntu server:  10.77.0.2
```

Адреса являются архитектурным резервом и должны быть проверены на отсутствие
пересечения с реальными LAN/Docker-подсетями перед вводом в эксплуатацию.

### Публичный HTTPS path

Обычные Windows-клиенты Face Moment не используют VPN:

```text
Windows / Chromium
        │
        │ HTTPS :443
        ▼
Public VPS / Caddy
        │
        │ private route over IPsec
        ▼
Kubuntu / Face Moment
```

Caddy:

- завершает публичный TLS;
- обслуживает публичный HTTPS-origin Face Moment;
- проксирует только необходимые HTTP endpoints через IPsec к центральному
  серверу;
- должен передавать request body потоково, без обязательной полной буферизации
  multipart-upload на VPS;
- не предоставляет клиентам прямой доступ к PostgreSQL, MinIO, Docker API или
  внутренним process ports;
- может отдавать `502/503`, если центральный сервер или IPsec-backhaul
  недоступен.

Публичный домен и точные upstream-порты будут зафиксированы после развёртывания.

### Почему Windows-клиенты не входят в VPN

Рабочий клиентский путь Face Moment намеренно оставлен обычным HTTPS:

- мобильные роутеры и CGNAT видят стандартный TCP/443;
- не требуется устанавливать и обслуживать VPN-профиль на каждом Windows
  клиенте;
- изменение внешнего IP мобильного роутера не требует перестройки
  client-side IKEv2-сеанса;
- локальный Chromium продолжает напрямую обращаться к локальному
  `ESP32.local`;
- QR/телефонный public flow использует ту же публичную HTTPS-границу;
- сложность VPN сосредоточена в одном постоянном Linux↔Linux backhaul.

### Локальная сеть SpaPromoClient

Локальный sensor path не проходит через VPS:

```text
ESP32.local
     ▲
     │ LAN
     │
Windows / Chromium
     │
     └──── HTTPS → VPS → IPsec → Kubuntu
```

Таким образом, VPN не должен менять `.local`/mDNS-маршрутизацию и не должен
перехватывать локальный трафик SpaPromoClient.

### Публично разрешённые и запрещённые сервисы

Базовая политика:

| Сервис | Доступ из интернета |
|---|---|
| Face Moment HTTPS | Да, через Caddy |
| IKEv2/IPsec | Да, UDP 500/4500 |
| SSH VPS | Ограниченный административный доступ |
| SSH Kubuntu | Нет напрямую |
| PostgreSQL | Нет |
| MinIO API/console | Нет |
| Docker API/socket | Нет |
| Backend internal ports | Нет напрямую |
| RealtimeFaceService internal port | Нет напрямую |

Административный доступ к центральному серверу в будущем может идти либо через
отдельный IKEv2 road-warrior профиль на VPS, либо через другой строго
контролируемый management path. Это не должно менять публичную архитектуру
Face Moment.

### Потоки данных Face Moment

#### Realtime SpaPromo

```text
Camera
  │
  ▼
Windows / Chromium
  │ local BlazeFace + JPEG crops
  │ HTTPS multipart, максимум 20 MiB
  ▼
VPS / Caddy
  │
  │ IPsec backhaul
  ▼
Kubuntu / RealtimeFaceService
  │
  ▼
result / teasers / QR data
  │
  └──────────── обратно по тому же пути
```

#### Загрузка фотографий фотографом

```text
Photographer browser
        │
        │ HTTPS
        ▼
VPS / Caddy
        │
        │ IPsec
        ▼
Kubuntu / backend
        ├── PostgreSQL
        └── private MinIO
```

Каждый JPEG принимается приложением независимо. Устойчивость больших загрузок
должна проверяться на реальном мобильном канале; VPN не заменяет корректную
обработку сетевых ошибок самим HTTP/client flow.

### Ответственность VPS и центрального сервера

| Функция | VPS | Kubuntu |
|---|---:|---:|
| Публичный IPv4 | Да | Нет |
| Публичный TLS endpoint | Да | Нет |
| Caddy reverse proxy | Да | Нет |
| IKEv2 responder / VPN hub | Да | Нет |
| IKEv2 initiator за CGNAT | Нет | Да |
| Face Moment backend | Нет | Да |
| RealtimeFaceService | Нет | Да |
| BackgroundPhotoWorker | Нет | Да |
| PostgreSQL + pgvector | Нет | Да |
| MinIO | Нет | Да |
| CPU face inference | Нет | Да |

## Пользователи и доступ центрального сервера

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

- UID/GID: `1002/1002`.
- Группы: `display`, `users`.
- Домашний каталог: `/home/display`, mode `750`.
- Пароль заблокирован.
- Не входит в `sudo` и `docker`.
- Не имеет доступа к `/opt/face-moment/.env`.
- Kiosk profile: `/home/display/.config/face-moment/kiosk-profile`, mode `700`,
  владелец `display`.
- Конечное назначение: SDDM autologin и запуск sandboxed Chromium через
  `spa-promo-client.service`.

## Docker

| Компонент | Состояние |
|---|---|
| Docker Engine | `29.7.2` |
| Docker Compose | `v5.5.0` |
| `docker.service` | active, enabled |
| Docker group | GID `975` |
| Default logging driver | `local`, `max-size=10m`, `max-file=5` |
| Проверка контейнера | `docker run --rm hello-world` успешно выполнена от `facemoment` |

Установлен Docker Engine, а не Docker Desktop.

## Размещение Face Moment

| Параметр | Значение |
|---|---|
| Compose project / deployment slug | `face-moment` |
| Checkout | `/opt/face-moment` |
| Владелец checkout | `facemoment:facemoment` |
| Mode checkout | `750` |
| Environment file | `/opt/face-moment/.env` |
| Mode environment file | `600` |
| Model assets | `/opt/face-moment/models/` |
| Mode model directory | `750` |
| Python package / PostgreSQL schema | `face_moment` |
| Edge HTTPS port | `8443` |

PostgreSQL, MinIO и модели являются внутренними ресурсами центрального сервера.
Секреты хранятся в `.env` и не включаются в этот файл.

## Системные настройки центрального сервера

| Настройка | Конфигурация |
|---|---|
| Sleep | `sleep.target` masked |
| Suspend | `suspend.target` masked |
| Hibernate | `hibernate.target` masked |
| Hybrid sleep | `hybrid-sleep.target` masked |
| Закрытие крышки | Игнорируется при любом типе питания и в docked mode |
| System idle action | `ignore` |
| Persistent journal limit | `SystemMaxUse=512M` |
| Runtime journal limit | `RuntimeMaxUse=128M` |
| SSD trim | `fstrim.timer` enabled |
| Автоматические security updates | `unattended-upgrades` enabled |
| Автоперезагрузка после обновлений | Отключена |

## Удалённый доступ и host-службы

| Компонент | Состояние |
|---|---|
| RustDesk system service | active, enabled |
| RustDesk restart policy | `Restart=always`, `RestartSec=5s` |
| RustDesk GUI/session | работает в графической сессии пользователя `face` |
| AnyDesk | active, enabled |
| Git | `/usr/bin/git` |
| `smartctl` | `/usr/sbin/smartctl` |
| `sensors` | `/usr/bin/sensors` |

До проверки административного SSH через приватный management path сохраняются
пользователь `face`, его временный SDDM autologin и RustDesk fallback.

После развёртывания VPS/IPsec следует отдельно проверить административный SSH
через приватный management path и только после этого рассматривать изменение
текущего RustDesk fallback.

## Что ещё нужно подтвердить для интеграции VPS

После завершения интеграции этот файл следует дополнить фактическими данными:

- провайдер и географический регион;
- сетевой лимит VPS;
- версия `Caddy`;
- время автоматического восстановления IPsec после обрыва;
- `iperf3` throughput через IPsec в обе стороны;
- RTT и packet loss;
- проверенный Path MTU;
- безопасное значение MSS clamp, если оно потребуется;
- скорость HTTPS upload через полный путь
  `Windows → VPS → IPsec → Kubuntu`;
- поведение при смене внешнего IP/переподключении мобильного роутера;
- автоматический startup после reboot обеих машин;
- firewall rules и отсутствие публичного доступа к внутренним сервисам.
