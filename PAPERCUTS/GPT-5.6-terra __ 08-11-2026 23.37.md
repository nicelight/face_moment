# Papercuts

- The host environment has no `python` executable; use the current disposable
  application image for Python-based integration probes.
- A Caddy `localhost` TLS site needs a probe with `localhost` SNI; an isolated
  Docker-network container name causes a TLS handshake failure before HTTP.
- A broad multi-file evidence patch was rejected after a protocol-state line
  had changed; split protocol updates into smaller context-anchored patches.
