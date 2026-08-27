# Журнал установки тестового сервера Face Moment

Последнее обновление: 2026-08-27

Подробные параметры машины находятся в [serverparams.md](serverparams.md).
Здесь фиксируются только ключевые этапы и важные findings.

## Ключевые этапы

| Этап | Статус | Findings |
|---|---|---|
| Kubuntu 26.04.1 LTS и KDE Plasma | выполнено | Система загружается; `Asia/Novosibirsk` соответствует физическому расположению |
| RustDesk | выполнено | После контрольной перезагрузки autologin и удалённый доступ восстановились; service policy `Restart=always` |
| Docker Engine и Compose | выполнено | Docker `29.7.2`, Compose `v5.5.0`; `hello-world` прошёл от `facemoment` |
| Административный пользователь | выполнено | `facemoment` имеет `sudo` и `docker`; доступ к Docker socket проверен |
| Проверка ОС и накопителя | выполнено | Failed units нет; NVMe SMART `PASSED`, ошибок носителя нет |
| Проверка сети и PCIe | частично выполнено | Текущая сеть — Wi-Fi Intel Wireless-AC 7265; массовый корректируемый PCIe `RxErr` остаётся наблюдаемым finding |
| Git checkout проекта | выполнено | Код размещён в `/opt/face-moment`; используется remote `main` |
| Compose configuration | выполнено | `docker compose config --quiet` прошёл без вывода |
| Сборка application image | выполнено | `docker compose build` завершился успешно |
| Ограничение system journal | выполнено | Persistent journal ограничен `512M`, runtime journal — `128M` |
| Непривилегированный пользователь `display` | выполнено | UID 1002, home mode `750`, группы `display` и `users`; доступа к `sudo` и Docker нет |
| Базовое server power management | выполнено | Sleep, suspend, hibernate и hybrid-sleep masked |
| Laptop 24/7 policy | выполнено | Закрытие крышки и system idle не останавливают сервер; конфигурация пережила контрольный reboot |
| Swap | выполнено | `/swapfile` увеличен с `512M` до `4G` |
| Автоматическое обслуживание | выполнено | `fstrim.timer` и `unattended-upgrades` enabled |
| Update reboot policy | выполнено | Автоматическая перезагрузка после package updates отключена |
| Изоляция display profile | выполнено | Profile mode `700`; пользователь `display` не читает deployment `.env` |
| Docker logging | выполнено | Default driver `local`; ротация `10m × 5` на контейнер |
| Временный Wi-Fi uplink | выполнено | Autoconnect без ограничения retries; постоянный MAC; power saving отключён |
| Временный recovery autologin | выполнено | SDDM автоматически запускает Plasma пользователя `face` при boot и после session exit |
| IPsec software stack | подготовлено | Установлены modern strongSwan `charon-systemd` и `swanctl`; tunnel configuration ещё не создавалась |
| Базовая подготовка VPS | выполнено | VPS обновлён до AlmaLinux 9.8; UTC, SELinux Enforcing и `firewalld`; публичный `cockpit` закрыт; SSH key и password authentication проверены после reboot |
| IPsec responder на VPS | выполнено | `strongSwan 6.0.6`, XFRM `ipsec0` `10.77.0.1/30`, UDP 500/4500 и ESP; сертификатная конфигурация загружена без ошибок |

## Текущее состояние

- VPS-сторона IPsec настроена; центральная сторона и установленный tunnel ещё
  не настроены.
- Административный SSH центрального сервера через приватный management path
  ещё не настроен.
- Chromium и autologin пользователя `display` не настраивались.
- Постоянные контейнеры проекта ещё не запускались.
- `.env` создан, проверен и имеет mode `600`.
- Модели ещё не размещались.
