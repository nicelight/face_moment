# MediaPipe Tasks Vision runtime

This release bundles the official `@mediapipe/tasks-vision` `1.0.1` browser
runtime required by `client/blazeface.js`. Only the SIMD loader and binary are
served because the managed Chromium target supports WebAssembly SIMD.

The runtime is intentionally local to the central-origin client bundle. It is
not loaded from a CDN at runtime, and it is the only client ML runtime.

Source package: `@mediapipe/tasks-vision@1.0.1`.

SHA-256:

- `vision_bundle.mjs`: `d885630c297c0b20b1fe86096cb06291c4c8080876f27852e724f24ac603713f`
- `wasm/vision_wasm_internal.js`: `e170ee67dd4e16c1a6fcd8840a206687e5a59b22c20e4a902bc445b095454d73`
- `wasm/vision_wasm_internal.wasm`: `8da277a733926eacd0474b8704b36742d6ec3231c57a860c5b889dff8f1df886`

The upstream package is Apache-2.0 licensed. Its source license text is
available at <https://www.apache.org/licenses/LICENSE-2.0>.
