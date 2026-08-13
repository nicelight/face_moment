- `docker image inspect --format` fails the entire template with `map has no
  entry for key "Entrypoint"` when `.Config.Entrypoint` is absent. Inspect only
  guaranteed fields or render `.Config` as JSON before querying optional keys.
