# Papercuts

- Во время поиска current accepted graph я предположил путь `.memory-bank/spec-graph.yaml`, которого в проекте нет; authoritative dependency graph фактически находится в `.memory-bank/contracts/boundary-map.md#dependency-graph`. Роутер `spec-index.md` не даёт прямого имени отдельного graph-файла, поэтому такой exploratory lookup создаёт лишний benign `rg` error.
