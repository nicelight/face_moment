from datetime import datetime, timezone

from face_moment.platform.staff_datetime import datetime_range_fields
from face_moment.diagnostics.http import _render_server_event_page


def test_default_controls_share_server_today_and_current_time_across_midnight() -> None:
    html = datetime_range_fields(now=datetime(2026, 9, 11, 20, 15, 30, tzinfo=timezone.utc))
    assert html.count('type="date"') == 2
    assert html.count('value="12.09.2026"') == 2
    assert html.count('data-time-picker') == 2
    assert 'type="time"' not in html
    assert html.count('value="03:15:30"') == 2
    assert 'data-range-enabled checked' not in html
    assert html.count('data-utc disabled') == 2


def test_bookmarked_utc_range_is_shown_as_utc_plus_seven() -> None:
    html = datetime_range_fields(from_value='2026-09-11T17:00:00Z', to_value='2026-09-11T18:30:15Z', max_days=7)
    assert 'id="from-date" type="text" data-date-text data-date value="12.09.2026"' in html
    assert 'id="from-time" type="text" data-time value="00:00:00"' in html
    assert 'id="to-time" type="text" data-time value="01:30:15"' in html
    assert 'data-range-enabled checked' in html
    assert 'data-max-days="7"' in html


def test_severity_and_component_options_include_all_and_keep_the_selection() -> None:
    html = _render_server_event_page([], [('severity', 'error'), ('component', 'qr')])
    assert '<select name="severity">' in html
    assert '<select name="component">' in html
    assert html.count('>all (Все)</option>') == 2
    assert 'value="error" selected>error (Ошибка)' in html
    assert 'value="qr" selected>qr (QR-переходы)' in html
    for value in ('runtime (Работа сервиса)', 'realtime (Распознавание)', 'promo (Показ фотографий)'):
        assert value in html


def test_display_timestamp_omits_microseconds_and_zone_suffix_in_utc_plus_seven() -> None:
    from face_moment.platform.staff_datetime import format_staff_datetime
    from face_moment.diagnostics.http import _iso
    instant = datetime(2026, 9, 11, 20, 5, 17, 501214, tzinfo=timezone.utc)
    assert format_staff_datetime(instant) == "12.09.2026 03:05:17"
    assert format_staff_datetime("2026-09-11T16:05:17.501214Z") == "11.09.2026 23:05:17"
    assert _iso(instant) == "12.09.2026 03:05:17"
