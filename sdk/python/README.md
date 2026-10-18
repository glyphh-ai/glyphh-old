# glyphh

Ada for Python. Your models live in your Glyphh runtime; this calls them at the runtime's address with a runtime key.

```bash
pip install glyphh
```

```python
from glyphh import Ada, AdaError

incidents = Ada().model("incidents")   # GLYPHH_RUNTIME_URL, GLYPHH_RUNTIME_KEY; or Ada(url, key)

incidents.record({"error": {...}, "resolution": {...}}, outcome="raise circuit breaker")

r = incidents.decide({"error": {"what": {"class": "TimeoutError", "message": "payment gateway timed out"}}})
if r.done:
    apply(r.data["fix"])
elif r.waiting:                        # needs_input or needs_approval: r.prompt says what
    r = incidents.resume(r.run_id, ask_someone(r.prompt))

bot = incidents.query({...}, clearance=0.5)   # a caller who may not see the secured layers
```

`GLYPHH_RUNTIME_URL` is the runtime's own address: `https://<machine>.glyphh.app` for one Glyphh hosts, or
`https://<host>` for one you host yourself. The key is made on the platform's Keys page (https://platform.glyphh.ai).

`Ada.models()`, `Ada.deploy(repo, commit)`, `Ada.run(run_id)`, `Ada.log(run_id)`, `Ada.cancel(run_id)`;
`Model.call(function, inputs, version=, clearance=)` reaches any function. A refusal raises `AdaError(code, message,
status)`: `E_AUTH`, `E_LIMIT`, `E_MODEL_MISSING`,
`E_RUN_MISSING`, `E_BAD_REQUEST`, `E_UNREACHABLE`. On a hosted runtime, a `record` past the plan's managed
precedents is a `failed` run whose `data.code` is `E_LIMIT_PRECEDENTS`. The contract both SDKs are tested against is
`../../contract`.

## 3.0.0: a new name, and a break

This package was `glyphh-ada` (`from glyphh_ada import Ada`) up to 0.4.0; it is `glyphh` now
(`from glyphh import Ada`). The API is the same; only the name and the import changed.

The name `glyphh` on PyPI is Glyphh's already: up to 2.6.7 it was the old HDC runtime (`glyphh-runtime`), a different
library with a different API. 3.0.0 is a major version so that nothing pinned to `glyphh<3` picks this up by
surprise: code written for 2.x does not run on 3.x. Pin `glyphh>=3` for this SDK.

`glyphh-ada` is removed from PyPI: `pip uninstall glyphh-ada && pip install glyphh`, then change `glyphh_ada` to
`glyphh` in your imports.

## License

MIT (`LICENSE`).
