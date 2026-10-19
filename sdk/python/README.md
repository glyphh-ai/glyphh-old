# glyphh

Ada for Python: calls the Ada models in your Glyphh runtime, at its address, with a runtime key. Python 3.9 or later,
no dependencies.

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

`GLYPHH_RUNTIME_URL` is the runtime's address: `https://<machine>.glyphh.app` (hosted) or `https://<host>`
(self-hosted). The key is made on the platform's API Keys page (https://platform.glyphh.ai).

| | |
|---|---|
| `Ada` | `models()`, `deploy(repo, commit, token=None)`, `model(name)`, `run(run_id)`, `log(run_id)`, `resume(run_id, answer)`, `cancel(run_id)` |
| `Model` | `record(data, outcome=None)`, `query`, `facts(top=)`, `probabilities`, `decide`, `learn(sample=)`, each with `clearance=`; `call(function, inputs, version=, clearance=)` for any function; `resume(run_id, answer)` |
| `Result` | `run_id`, `model`, `version`, `function`, `status`, `data`, `step`, `prompt`, `seconds`; `done`, `waiting`, `ended` |
| `AdaError` | `code`, `message`, `status`: the runtime's code (`E_AUTH`, `E_LIMIT`, `E_MODEL_MISSING`, `E_RUN_MISSING`, `E_BAD_REQUEST`, ...), `E_UNREACHABLE` or `E_CONFIG` |

On a hosted runtime, a `record` past the plan's managed precedents is a `failed` run whose `data.code` is
`E_LIMIT_PRECEDENTS`. The routes and the contract are in the [repository's README](https://github.com/glyphh-ai/glyphh#the-runtimes-rest-api).

Pin `glyphh>=3`: versions up to 2.6.7 are a different, older library.

## License

MIT (`LICENSE`).
