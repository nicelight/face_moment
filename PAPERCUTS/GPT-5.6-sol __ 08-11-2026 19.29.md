# Papercuts

- A diagnostic `node -e` command embedded a JavaScript template literal inside shell double quotes, so Bash expanded `${...}` and rejected it before Node ran. Use a quote-safe invocation for inline JavaScript containing template syntax.
