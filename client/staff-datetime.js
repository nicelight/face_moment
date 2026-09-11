/* Staff controls always use UTC+7, independently of the browser's timezone. */
(() => {
  const offsetMs = 7 * 60 * 60 * 1000;

  function formatTimestamp(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(value)) return value;
    const instant = new Date(value);
    if (!Number.isFinite(instant.getTime())) return value;
    const local = new Date(instant.getTime() + offsetMs).toISOString();
    return `${local.slice(0, 10).split('-').reverse().join('.')} ${local.slice(11, 19)}`;
  }

  function dateValue(input) {
    const match = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(input.value);
    if (!match || match[3] === '0000') return '';
    const iso = `${match[3]}-${match[2]}-${match[1]}`;
    const date = new Date(`${iso}T00:00:00Z`);
    return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === iso ? iso : '';
  }

  function setDate(input, iso) {
    input.value = iso ? iso.split('-').reverse().join('.') : '';
    input.closest('[data-date-picker]').querySelector('[data-calendar]').value = iso;
    input.setCustomValidity('');
  }

  function initDatePickers(root) {
    root.querySelectorAll('[data-date-picker]').forEach(picker => {
      if (picker.dataset.ready) return;
      picker.dataset.ready = 'true';
      const text = picker.querySelector('[data-date-text]');
      const calendar = picker.querySelector('[data-calendar]');
      text.addEventListener('input', () => {
        const iso = dateValue(text);
        calendar.value = iso;
        text.setCustomValidity(text.value && !iso ? 'Введите существующую дату в формате дд.мм.гггг.' : '');
      });
      calendar.addEventListener('change', () => {
        setDate(text, calendar.value);
        text.dispatchEvent(new Event('input', { bubbles: true }));
      });
    });
  }

  function timeValue(input) {
    const match = /^([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?$/.exec(input.value);
    return match ? `${match[1]}:${match[2]}:${match[3] ?? '00'}` : '';
  }

  function setTime(input, value) {
    input.value = value;
    input.setCustomValidity('');
  }

  function initTimePickers(root) {
    root.querySelectorAll('[data-time]').forEach(input => {
      if (input.dataset.ready) return;
      input.dataset.ready = 'true';
      input.addEventListener('input', () => {
        input.setCustomValidity(input.value && !timeValue(input) ? 'Введите время от 00:00:00 до 23:59:59.' : '');
      });
      input.addEventListener('blur', () => {
        const value = timeValue(input);
        if (value) input.value = value;
      });
      input.addEventListener('keydown', event => {
        if (!['ArrowUp', 'ArrowDown'].includes(event.key) || !timeValue(input)) return;
        event.preventDefault();
        const segment = Math.min(2, Math.floor((input.selectionStart ?? 0) / 3));
        const parts = timeValue(input).split(':');
        const limit = segment === 0 ? 24 : 60;
        parts[segment] = String((Number(parts[segment]) + (event.key === 'ArrowUp' ? 1 : -1) + limit) % limit).padStart(2, '0');
        input.value = parts.join(':');
        input.setSelectionRange(segment * 3, segment * 3 + 2);
        input.dispatchEvent(new Event('input', { bubbles: true }));
      });
    });
  }

  function toUtc(field) {
    const date = dateValue(field.querySelector('[data-date]'));
    const time = timeValue(field.querySelector('[data-time]'));
    if (!date || !time) return '';
    const instant = new Date(`${date}T${time}+07:00`);
    return Number.isFinite(instant.getTime()) ? instant.toISOString() : '';
  }

  function sync(form) {
    let valid = true;
    for (const range of form.querySelectorAll('[data-datetime-range]')) {
      const enabled = range.querySelector('[data-range-enabled]').checked;
      const fields = [...range.querySelectorAll('[data-datetime-field]')];
      const values = fields.map(field => {
        const input = field.querySelector('[data-utc]');
        input.disabled = !enabled;
        input.value = enabled ? toUtc(field) : '';
        field.querySelectorAll('[data-date], [data-time]').forEach(control => { control.required = enabled; if (!enabled) control.setCustomValidity(''); });
        return input.value;
      });
      let error = '';
      if (enabled) {
        if (values.some(value => !value)) error = 'Выберите дату и время начала и окончания.';
        else if (values[0] >= values[1]) error = 'Окончание периода должно быть позже начала.';
        else if (range.dataset.maxDays && Date.parse(values[1]) - Date.parse(values[0]) > Number(range.dataset.maxDays) * 86400000) {
          error = `Выберите период не длиннее ${range.dataset.maxDays} дней.`;
        }
      }
      range.querySelector('[data-range-error]').textContent = error;
      if (error) valid = false;
    }
    return valid;
  }

  function init(form) {
    initDatePickers(form);
    initTimePickers(form);
    if (form.dataset.datetimeReady) return;
    form.dataset.datetimeReady = 'true';
    for (const range of form.querySelectorAll('[data-datetime-range]')) {
      range.addEventListener('input', event => {
        if (event.target.matches('[data-date], [data-time]')) range.querySelector('[data-range-enabled]').checked = true;
        sync(form);
      });
    }
    form.addEventListener('submit', event => {
      if (!sync(form)) {
        event.preventDefault();
        event.stopImmediatePropagation();
        form.querySelector('[data-range-error]:not(:empty)')?.scrollIntoView({ block: 'nearest' });
        return;
      }
    }, true);
    form.addEventListener('formdata', event => {
      for (const [name, value] of [...event.formData.entries()]) {
        if (value === '') event.formData.delete(name);
      }
    });
    sync(form);
  }

  function setValue(form, name, utcValue) {
    const input = form.elements.namedItem(name);
    if (!input?.matches('[data-utc]')) return false;
    const instant = new Date(utcValue);
    if (!Number.isFinite(instant.getTime())) return false;
    const local = new Date(instant.getTime() + offsetMs).toISOString();
    const field = input.closest('[data-datetime-field]');
    setDate(field.querySelector('[data-date]'), local.slice(0, 10));
    setTime(field.querySelector('[data-time]'), local.slice(11, 19));
    field.closest('[data-datetime-range]').querySelector('[data-range-enabled]').checked = true;
    sync(form);
    return true;
  }

  window.StaffDateTime = { init, sync, setValue, dateValue, setDate, formatTimestamp };
  document.addEventListener('DOMContentLoaded', () => {
    initDatePickers(document);
    document.querySelectorAll('form').forEach(form => {
      if (form.querySelector('[data-datetime-range]')) init(form);
    });
  });
})();
