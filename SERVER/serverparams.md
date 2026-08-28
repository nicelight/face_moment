# Параметры серверной инфраструктуры Face Moment

Последнее обновление: 2026-08-28

## Топология

```text
Chromium-клиенты
    │ HTTPS :443
    ▼
VPS 46.8.200.99 / Caddy
    │ loopback 127.0.0.1:18443
    ▼
FRP: frps ← WSS/TLS :443 ← frpc
    │
    ▼
Центральный сервер face-pc / 127.0.0.1:8443
```

- VPS — единственная публичная точка входа.
- Центральный сервер находится за NAT/CGNAT и устанавливает только исходящее
  WSS-соединение к VPS.
- Клиентам нужен только Chromium и обычный HTTPS; VPN/FRP на клиентах не нужен.
- PostgreSQL, MinIO, Docker API и внутренние порты центрального сервера наружу
  не публикуются.

## Центральный сервер

### Платформа

| Параметр | Значение |
|---|---|
| Hostname | `face-pc` |
| ОС | Kubuntu / Ubuntu 26.04.1 LTS |
| Kernel | `Linux 7.0.0-30-generic` |
| Архитектура | `x86-64` |
| CPU | Intel Core i7-8850H, 6 ядер / 12 потоков, AVX/AVX2 |
| RAM | 15 GiB |
| Swap | 4 GiB, `/swapfile` |
| Системный диск | NVMe 238.5 GiB, root `ext4` |
| Свободно на root при проверке | около 206 GiB |
| Часовой пояс | `Asia/Novosibirsk` (`UTC+07:00`) |
| Синхронизация времени | NTP active, RTC в UTC |

### Сеть

| Интерфейс | Состояние | Адрес |
|---|---|---|
| `wlp4s0` | UP | DHCP `192.168.3.57/24` |
| `enp3s0` | DOWN | адрес не назначен |

- Default route: `192.168.3.1` через `wlp4s0`.
- Локальный IPv4 динамический; публичный IPv4 центральному серверу не нужен.
- Входящий port forwarding на роутере не требуется.
- UFW установлен, но неактивен.

### Пользователи и runtime

| Пользователь | Назначение |
|---|---|
| `face` | bootstrap/admin, графическая KDE-сессия |
| `facemoment` | приложение, Docker и deployment |
| `display` | kiosk-сессия Chromium без `sudo` и доступа к секретам |

| Компонент | Значение |
|---|---|
| Docker Engine | `29.7.2`, active/enabled |
| Docker Compose | `v5.5.0` |
| Deployment root | `/opt/face-moment` |
| Environment file | `/opt/face-moment/.env`, mode `600` |
| Model directory | `/opt/face-moment/models/` |
| Планируемый локальный HTTPS edge | `127.0.0.1:8443` |
| FRP client | `frpc 0.70.1`, active/enabled |
| FRP config | `/etc/frp/frpc.toml` |
| FRP token | `/etc/frp/client_token`, отдельный закрытый файл |
| OpenSSH | active/enabled; key-based вход через FRP/VPS проверен |

### Host-настройки

| Настройка | Состояние |
|---|---|
| Sleep/suspend/hibernate | отключены через masked systemd targets |
| Закрытие крышки | игнорируется |
| Persistent journal | максимум 512 MiB |
| Runtime journal | максимум 128 MiB |
| SSD trim | `fstrim.timer` enabled |
| Security updates | `unattended-upgrades` enabled, autoreboot выключен |
| Резервный удалённый доступ | RustDesk и AnyDesk active/enabled |

## VPS

### Платформа

| Параметр | Значение |
|---|---|
| Hostname | `igornskprod-alma9` |
| ОС | AlmaLinux 9.8 |
| Kernel | `Linux 5.14.0-687.41.1.el9_8.x86_64` |
| Виртуализация | VMware |
| CPU | 2 vCPU, AMD EPYC 9654 |
| RAM | 1.7 GiB |
| Swap | 190 MiB |
| Диск | 20 GiB, root `ext4` |
| Публичный IPv4 | `46.8.200.99` |
| Часовой пояс | UTC, NTP synchronized |
| SELinux | Enforcing |

### Публичные сервисы

| Компонент | Значение |
|---|---|
| Домен | `face-time.moment-studio.ru` |
| DNS A | `46.8.200.99` |
| Public HTTPS | Caddy `2.11.4`, TCP `443` |
| TLS | Let's Encrypt, сертификат получен и проверен |
| FRP server | `frps 0.70.1`, active/enabled |
| SSH | `root`, key и password authentication |
| Вход с рабочей машины | `ssh igornskprod` → `root@46.8.200.99:22` |
| Firewall | firewalld/nftables; публичны только `http`, `https`, `ssh` |
| Docker | не используется |

### Пути конфигурации VPS

| Компонент | Путь |
|---|---|
| Caddy | `/etc/caddy/Caddyfile` |
| Caddy environment | `/etc/caddy/face-moment.env` |
| FRP server | `/etc/frp/frps.toml` |
| FRP token | `/etc/frp/server_token` |
| Caddy service override | `/etc/systemd/system/caddy.service.d/face-moment.conf` |

## FRP и маршрутизация

### WSS control channel

| Параметр | Значение |
|---|---|
| Направление | `face-pc/frpc` → VPS/Caddy → `frps` |
| Transport | WSS/TLS поверх TCP `443` |
| Public hostname | `face-time.moment-studio.ru` |
| WSS path | `/~!frp` |
| `frps` bind | `127.0.0.1:7000` на VPS |
| Аутентификация | token из отдельных mode `600` файлов |
| Переподключение | автоматически через systemd/FRP |

### Reverse endpoints на VPS

| Endpoint | Назначение | Публикация |
|---|---|---|
| `127.0.0.1:18443` | HTTP/HTTPS приложения → `face-pc:8443` | только loopback VPS |
| `127.0.0.1:10022` | административный SSH → `face-pc:22` | только loopback VPS |

`frps` использует `proxyBindAddr = "127.0.0.1"`, поэтому reverse endpoints не
слушают публичный интерфейс VPS и не требуют firewall rules.

## Клиентский HTTPS path

```text
Chromium
  → https://face-time.moment-studio.ru:443
  → VPS Caddy
  → 127.0.0.1:18443 на VPS
  → FRP/WSS
  → 127.0.0.1:8443 на face-pc
```

Caddy завершает публичный TLS и передаёт запросы через FRP. Публичный TLS и
WSS login подтверждены. Пока приложение не слушает `127.0.0.1:8443`, обычный
HTTPS-запрос ожидаемо получает `502`.

## Административный SSH path

С рабочей машины используются две команды:

```bash
ssh igornskprod
ssh facecentral
```

- `ssh igornskprod` подключается непосредственно к VPS как `root` по TCP `22`.
- `ssh facecentral` использует `igornskprod` как OpenSSH `ProxyJump`, затем
  обращается к loopback endpoint `127.0.0.1:10022` на VPS и через FRP попадает
  в OpenSSH центрального сервера как пользователь `face`.
- Оба alias настроены в локальном `/home/serg/.ssh/config` рабочей машины.

```text
Рабочий компьютер
  → SSH ProxyJump `igornskprod`
  → 127.0.0.1:10022 на VPS
  → FRP/WSS
  → 127.0.0.1:22 на face-pc
```

Проверенная команда входа на центральный сервер:

```bash
ssh facecentral
```

Проверка показала, что порт `10022` слушает только `127.0.0.1` на VPS. В
firewalld он не открыт и на публичном адресе `46.8.200.99` не слушает.

## Текущий статус

| Узел | Статус |
|---|---|
| DNS → VPS | работает |
| HTTPS/TLS на VPS | работает |
| `frpc` WSS login → `frps` | подтверждён |
| Application endpoint `face-pc:8443` | ожидает готового приложения |
| SSH endpoint `face-pc:22` через VPS | проверен: `ssh facecentral` входит как `face` на `face-pc` |
