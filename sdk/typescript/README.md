# @glyphh-ai/glyphh

Ada for TypeScript and JavaScript. Your models live in your Glyphh runtime; this calls them at the runtime's address
with a runtime key.

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

`GLYPHH_RUNTIME_URL` is the runtime's own address: `https://<machine>.glyphh.app` for one Glyphh hosts, or
`https://<host>` for one you host yourself. The key is made on the platform's Keys page (https://platform.glyphh.ai).

`ada.models()`, `ada.deploy(repo, commit)`, `ada.run(runId)`, `ada.log(runId)`, `ada.cancel(runId)`;
`model.call(fn, inputs, { version, clearance })` reaches any function. A refusal throws `AdaError` (`code`, `message`,
`status`): `E_AUTH`, `E_LIMIT`, `E_MODEL_MISSING`,
`E_RUN_MISSING`, `E_BAD_REQUEST`, `E_UNREACHABLE`. On a hosted runtime, a `record` past the plan's managed
precedents is a `failed` run whose `data.code` is `E_LIMIT_PRECEDENTS`. The contract both SDKs are tested against is
`../../contract`.

## 3.0.0: a new name

This package was `@glyphh-ai/ada` up to 0.4.0; it is `@glyphh-ai/glyphh` now, at 3.0.0 to keep one version with the
Python SDK (`glyphh` on PyPI, where 3.0.0 is a break from the old 2.x library of that name). The API is the same:
change the import. `@glyphh-ai/ada` is deprecated and gets no new versions.

## License

MIT (`LICENSE`).
