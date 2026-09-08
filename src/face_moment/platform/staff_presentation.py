"""Shared staff presentation; capability handlers retain their routes and authority.

@docs .design/motion-atlas-integration/DESIGN_BRIEF.md
"""
from __future__ import annotations

from html import escape
import re

from face_moment.platform.auth.principals import StaffPrincipal

PAGES: dict[str, tuple[str, str]] = {
    "login": ("С возвращением", "Войдите в рабочее пространство Face Moment."),
    "home": ("Всё для ваших кадров", "Фотографии, экраны и обработка — в одном рабочем пространстве."),
    "photo-upload": ("Загрузка фотографий", "Выберите площадку и дату съёмки. Добавьте фотографии — обработка начнётся автоматически."),
    "photo-inventory": ("Библиотека фотографий", "Свежие поступления, результаты обработки и управление скрытыми фотографиями."),
    "processing-health": ("Состояние обработки", "Очередь фотографий, время обработки и доступное место в хранилищах."),
    "display-clients": ("Экраны", "Настроенные киоски и доступ для подключения Chromium-клиентов."),
    "search-settings": ("Настройки поиска", "Укажите дату посещения, по которой экран будет искать фотографии."),
    "attempts": ("История поиска", "Попытки распознавания и результаты — от захвата до показа фотографий."),
    "attempt-detail": ("Подробности поиска", "Результат, этапы обработки и диагностические материалы попытки."),
    "server-events": ("События сервера", "Поиск по структурированному журналу событий."),
    "calibrations": ("Калибровка", "Проверка качества поиска на подготовленных примерах."),
    "calibration-detail": ("Результаты калибровки", "Сохранённые результаты и параметры применения."),
    "annotations": ("Разметка лиц", "Проверьте найденные лица и добавьте пропущенные области."),
    "diagnostics-retention": ("Хранение диагностики", "Последний результат очистки диагностических материалов."),
}

# The role list only controls presentation. Existing endpoints enforce access.
NAVIGATION = (
    ("photo-upload", "Загрузить фото", "photographer", "Добавить фотографии с новой съёмки."),
    ("photo-inventory", "Библиотека", "photographer operator developer", "Поступления и результаты обработки."),
    ("processing-health", "Обработка", "operator developer", "Очередь, скорость и состояние хранилищ."),
    ("display-clients", "Экраны", "operator developer", "Подключение и настройки киосков."),
    ("search-settings", "Настройки поиска", "operator", "Площадка и активная дата посещения."),
    ("attempts", "История поиска", "operator developer", "Результаты попыток распознавания."),
    ("server-events", "События сервера", "developer", "Подробный журнал работы системы."),
    ("calibrations", "Калибровка", "developer", "Проверка и настройка качества поиска."),
    ("diagnostics-retention", "Хранение диагностики", "operator developer", "Результаты очистки материалов."),
)

def fluid_markup() -> str:
    return '<div class="fm-fluid" aria-hidden="true">' + '<i class="fm-fluid-spot"></i>' * 4 + '</div>'

def brand_markup(href: str = "/staff") -> str:
    return f'<a class="fm-brand" href="{escape(href, quote=True)}" aria-label="Face Moment — главная"><span class="fm-brand-mark" aria-hidden="true"></span><span class="fm-brand-name">face<span>moment</span></span></a>'

def _header(page: str) -> str:
    links = ''.join(
        f'<a href="/staff/{key}" data-staff-roles="{roles}" hidden'
        + (' aria-current="page"' if page == key else '') + f'>{label}</a>'
        for key, label, roles, _ in NAVIGATION
    )
    navigation = '<a class="fm-eyebrow" href="/site">На сайт ↗</a>' if page == "login" else f'''<details class="fm-nav">
      <summary>Меню</summary><nav class="fm-nav-links" aria-label="Рабочее пространство">
      <div class="fm-identity" id="staff-identity">Рабочее пространство</div>
      <a href="/staff"{' aria-current="page"' if page == 'home' else ''}>Главная</a>{links}
      <a href="/display">Открыть экран ↗</a><a href="/site">На сайт ↗</a>
      <button id="staff-logout" type="button">Выйти</button></nav></details>'''
    return f'<a class="fm-skip-link" href="#staff-content">К содержимому</a><header class="fm-header">{brand_markup()}<span class="fm-tag">Рабочее пространство</span>{navigation}</header>'

def staff_document(document: str, page: str) -> str:
    """Decorate the existing complete page without rewriting forms or scripts."""
    title, description = PAGES[page]
    if '<html' not in document:
        document = f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title></head><body>{document}</body></html>'
    document = document.replace('lang="en"', 'lang="ru"', 1)
    document = re.sub(r'<title>.*?</title>', lambda _: f'<title>{title} · Face Moment</title>', document, count=1)
    assets = '<link rel="stylesheet" href="/client/motion-theme.css"><script type="module" src="/client/staff-ui.js"></script>'
    document = document.replace('</head>', assets + '</head>', 1)
    classes = 'fm-page fm-staff' + (' fm-login' if page == 'login' else '')
    document = document.replace('<body>', f'<body class="{classes}" data-staff-page="{page}">' + _header(page), 1)
    heading = f'<header class="fm-page-heading"><p class="fm-eyebrow fm-kicker">Рабочее пространство</p><h1>{title}</h1><p>{description}</p></header>'
    if page == "login":
        art = '<section class="fm-login-art"><div class="fm-aurora" aria-hidden="true"><i></i><i></i><i></i></div><p class="fm-eyebrow">FACE MOMENT / STUDIO</p><h2>За каждым кадром —<br>ваша работа.</h2><p class="fm-eyebrow">Моменты, которые остаются</p></section>'
        document = document.replace('<main>', '<main id="staff-content">' + art + '<div class="fm-login-panel"><p class="fm-eyebrow fm-kicker">Доступ для команды</p>', 1)
        document = document.replace('<h1>Staff login</h1>', f'<h1>{title}</h1><p>{description}</p>', 1)
        document = document.replace('</main>', '</div></main>', 1)
    elif page != "home":
        document = document.replace('<main>', '<main id="staff-content">' + heading, 1)
    footer = '<footer class="fm-footer"><span>© Face Moment · Моменты, которые остаются</span><a href="/site">Перейти на сайт ↗</a></footer>'
    return document.replace('</body>', footer + '</body>', 1)

def staff_home_document(principal: StaffPrincipal) -> str:
    role = principal.role.value
    role_name = {"photographer": "Фотограф", "operator": "Оператор", "developer": "Разработчик"}[role]
    cards = ''.join(
        f'<a class="fm-action-card" href="/staff/{key}"><span class="fm-action-number">{i:02d}<span aria-hidden="true">↗</span></span><h3>{label}</h3><p>{description}</p></a>'
        for i, (key, label, roles, description) in enumerate(NAVIGATION, 1)
        if role in roles.split()
    )
    action = '/staff/photo-upload' if role == 'photographer' else '/staff/processing-health'
    action_label = 'Загрузить фотографии' if role == 'photographer' else 'Проверить обработку'
    content = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Рабочее пространство</title></head><body>
    <main class="fm-dashboard fm-container" id="staff-content">
      <section class="fm-hero">{fluid_markup()}<div class="fm-hero-content">
        <p class="fm-eyebrow fm-kicker">FACE MOMENT / ВАШЕ ПРОСТРАНСТВО</p>
        <h1>Всё для<br>ваших <em>кадров.</em></h1><p>Здесь начинается путь фотографии.<br>От загрузки — до встречи со своим героем.</p>
      </div><div class="fm-hero-footer"><a class="fm-button" href="{action}">{action_label}<span class="fm-button-arrow" aria-hidden="true">↗</span></a><span class="fm-hero-index">STUDIO / 01</span></div>
      </section>
      <div class="fm-summary-line"><span>Вы вошли как <strong>{escape(principal.username)}</strong></span><span>{role_name}</span></div>
      <section class="fm-workspace"><div class="fm-section-heading"><h2>К работе</h2><span class="fm-eyebrow">Всё под рукой</span></div><div class="fm-action-grid">{cards}</div></section>
    </main></body></html>'''
    return staff_document(content, 'home')
