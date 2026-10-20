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
| `Result` | `run_id`, `model`, `version`, `function`, `status`, `data`, `step`, `prompt`, `seconds`; `done`, `waiting`, `ended`, `limit_exceeded` |
| `AdaError` | `code`, `message`, `status`, `detail`, `retry_after`: the runtime's code (`E_AUTH`, `E_LIMIT`, `E_MODEL_MISSING`, `E_RUN_MISSING`, `E_BAD_REQUEST`, ...), `E_UNREACHABLE` or `E_CONFIG` |

In a cluster (self-hosted rrotor, several nodes behind a load balancer) the client:

- retries `E_NO_HEAD` (no head for a moment: writes wait, reads go on), and a read the runtime could not answer,
  with backoff and `Retry-After`, for up to `Ada(retry_deadline=)` seconds (default 30; 0: never). A write that
  may have been applied is never sent again.
- sends the highest `Rrotor-Cluster-Seq` it has seen as `Rrotor-Min-Seq`, so reads see its writes on any node
  (`Ada(read_your_writes=False)` to stop; `ada.cluster_seq` shows it).
- raises `NoHeadError`, `HeadLostError` (the head went with the write, which may have been applied: check before resending), `NotCommittedError` (the write is kept and commits later: do not resend it), `RunLostError`
  (the run's node left) and `ReadOnlyError` (a function marked `"writes": false` wrote), each an `AdaError`.

A `record` past the licence key's precedent cap (5,000 per node with no key) is `done` with `r.limit_exceeded` true:
nothing was indexed, and `r.data` says why. It is not raised and not a `failed` run. The routes and the contract are in the [repository's README](https://github.com/glyphh-ai/glyphh#the-runtimes-rest-api).

Pin `glyphh>=3`: versions up to 2.6.7 are a different, older library.

## License

MIT (`LICENSE`).
