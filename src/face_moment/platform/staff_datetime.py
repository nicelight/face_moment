"""Shared staff date/time controls in the operator's fixed UTC+7 timezone."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape

STAFF_TIMEZONE = timezone(timedelta(hours=7))


def staff_today() -> str:
    return datetime.now(STAFF_TIMEZONE).date().isoformat()


def date_picker(input_id: str, value: str, *, name: str = "", range_date: bool = False) -> str:
    """Fixed-format text field with a native calendar alongside it."""
    display = ".".join(reversed(value.split("-"))) if value else ""
    return f'''<span class="fm-date-picker" data-date-picker>
<input id="{escape(input_id)}" type="text"{' name="' + escape(name) + '"' if name else ''} data-date-text{' data-date' if range_date else ''} value="{escape(display)}" placeholder="дд.мм.гггг" pattern="[0-9]{{2}}[.][0-9]{{2}}[.][0-9]{{4}}" maxlength="10" required>
<span class="fm-calendar-icon" aria-hidden="true"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18"/></svg></span>
<input type="date" class="fm-calendar-native" data-calendar value="{escape(value)}" aria-label="Выбрать дату в календаре" title="Выбрать дату в календаре">
</span>'''


def time_picker(input_id: str, value: str) -> str:
    parts = value.split(":")
    controls = []
    for index, (part, label, count) in enumerate((("hour", "Часы", 24), ("minute", "Минуты", 60), ("second", "Секунды", 60))):
        options = "".join(
            f'<option value="{number:02d}"{" selected" if number == int(parts[index]) else ""}>{number:02d}</option>'
            for number in range(count)
        )
        controls.append(f'<select data-{part} aria-label="{label}">{options}</select>')
    return f'''<span class="fm-time-picker" data-time-picker>
{'<span aria-hidden="true">:</span>'.join(controls)}
<input id="{escape(input_id)}" type="hidden" data-time value="{escape(value)}">
</span>'''


def datetime_range_fields(
    *,
    from_name: str = "from",
    to_name: str = "to",
    from_label: str = "From",
    to_label: str = "To",
    from_value: str = "",
    to_value: str = "",
    max_days: int | None = None,
    now: datetime | None = None,
) -> str:
    current = (now or datetime.now(STAFF_TIMEZONE)).astimezone(STAFF_TIMEZONE)
    enabled = bool(from_value or to_value)
    fields = []
    for name, label, value in (
        (from_name, from_label, from_value), (to_name, to_label, to_value),
    ):
        selected = datetime.fromisoformat(value.upper().replace("Z", "+00:00")).astimezone(STAFF_TIMEZONE) if value else current
        prefix = escape(name)
        fields.append(f'''<fieldset class="fm-datetime-field" data-datetime-field>
<legend>{escape(label)} <span>UTC+7</span></legend>
<div class="fm-datetime-row">
<label for="{prefix}-date">Дата{date_picker(name + "-date", selected.date().isoformat(), range_date=True)}</label>
<label>Время (24 часа){time_picker(name + "-time", selected.strftime("%H:%M:%S"))}</label>
</div>
<input type="hidden" name="{prefix}" value="{escape(value)}" data-utc{'' if enabled else ' disabled'}>
</fieldset>''')
    return f'''<div class="fm-datetime-range" data-datetime-range data-max-days="{max_days or ''}">
<label class="fm-range-toggle"><input type="checkbox" data-range-enabled{' checked' if enabled else ''}>Применять период</label>
{''.join(fields)}
<p class="fm-range-hint">Выберите начало раньше окончания. Время указано в UTC+7.</p>
<p data-range-error role="alert"></p>
</div>'''
