# @glyphh-ai/glyphh

Ada for TypeScript and JavaScript: calls the Ada models in your Glyphh runtime, at its address, with a runtime key.
Node 18 or later (or any runtime with `fetch`), no dependencies.

```bash
npm install @glyphh-ai/glyphh
```

```ts
import { Ada, AdaError } from "@glyphh-ai/glyphh";

const incidents = new Ada().model("incidents");   // GLYPHH_RUNTIME_URL, GLYPHH_RUNTIME_KEY; or new Ada({ url, key })

await incidents.record({ error: {...}, resolution: {...} }, "raise circuit breaker");

let r = await incidents.decide<{ fix: string }>({ error: { what: { class: "TimeoutError", message: "payment gateway timed out" } } });
if (r.status === "done") apply(r.data.fix);
else if (r.status === "needs_input") r = await incidents.resume(r.run_id, await askSomeone(r.prompt));

const bot = await incidents.query({...}, { clearance: 0.5 });   // a caller who may not see the secured layers
```

`GLYPHH_RUNTIME_URL` is the runtime's address: `https://<machine>.glyphh.app` (hosted) or `https://<host>`
(self-hosted). The key is made on the platform's API Keys page (https://platform.glyphh.ai).

| | |
|---|---|
| `Ada` | `models()`, `deploy(repo, commit, token?)`, `model(name)`, `run(runId)`, `log(runId)`, `resume(runId, answer)`, `cancel(runId)` |
| `AdaModel` | `record(data, outcome?)`, `query`, `facts({ top })`, `probabilities`, `decide`, `learn({ sample })`, each with `{ clearance }`; `call(fn, inputs, { version, clearance })` for any function; `resume(runId, answer)` |
| `Result` | `run_id`, `model`, `version`, `function`, `status`, `data`, `step`, `prompt`, `seconds`, `limit_exceeded` |
| `AdaError` | `code`, `message`, `status`, `detail`, `retryAfter`: the runtime's code (`E_AUTH`, `E_LIMIT`, `E_MODEL_MISSING`, `E_RUN_MISSING`, `E_BAD_REQUEST`, ...), `E_UNREACHABLE` or `E_CONFIG` |

In a cluster (self-hosted rrotor, several nodes behind a load balancer) the client:

- retries `E_NO_HEAD` (no head for a moment: writes wait, reads go on), and a read the runtime could not answer,
  with backoff and `Retry-After`, for up to `new Ada({ retryDeadline })` seconds (default 30; 0: never). A write
  that may have been applied is never sent again.
- sends the highest `Rrotor-Cluster-Seq` it has seen as `Rrotor-Min-Seq`, so reads see its writes on any node
  (`readYourWrites: false` to stop; `ada.clusterSeq` shows it).
- throws `NoHeadError`, `HeadLostError` (the head went with the write, which may have been applied: check before resending), `NotCommittedError` (the write is kept and commits later: do not resend it), `RunLostError`
  (the run's node left) and `ReadOnlyError` (a function marked `"writes": false` wrote), each an `AdaError`.

A self-hosted `record` past the licence key's precedent cap is `done` with `r.limit_exceeded` true: nothing was
indexed, and `r.data` says why. On a hosted runtime, a `record` past the plan's managed precedents is a `failed` run
whose `data.code` is `E_LIMIT_PRECEDENTS`. The routes and the contract are in the
[repository's README](https://github.com/glyphh-ai/glyphh#the-runtimes-rest-api).

## License

MIT (`LICENSE`).
