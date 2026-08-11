# Papercuts

- `functions.exec` завершил JavaScript-cell после того, как вложенный `exec_command` уже вернул собственный `session_id`; ожидание через `functions.wait` наблюдало cell, а не PTY-команду, поэтому первые два запуска disposable probe выглядели завершёнными без результата. Потребовалось повторить запуск и продолжить именно `session_id` через `write_stdin`.
- На host отсутствует команда `python`, хотя `python3` доступна; первая попытка разобрать свежий `caddy adapt` через pipe завершилась после успешного `caddy validate` ошибкой `python: command not found` и потребовала повторить только parsing-команду с `python3`.
