# Papercuts

- The host PATH has no `python` executable, so a planned in-process RED probe
  failed before importing the application. Use `python3` or the project
  container explicitly; do not treat the setup failure as RED evidence.
- The available host `python3` is an unprovisioned 3.14 interpreter without
  FastAPI. Run task application probes inside the project container instead.
- The host browser does not trust the disposable Caddy `tls internal` CA. A
  task-local Playwright CLI config with `ignoreHTTPSErrors: true` is needed for
  the isolated HTTPS UAT; the initial certificate error is setup-only evidence.
- The Playwright CLI `run-code` sandbox lacks a global `setTimeout`. Use the
  Playwright `page.waitForTimeout()` API in task-local UAT drivers instead;
  the failed callback occurred before a browser-flow claim result.
- The command sandbox rejects `rm -f` even for validated task-owned generated
  artifacts. Move superseded evidence into an explicitly named task-local
  directory instead of deleting it in place.
