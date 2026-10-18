# Glyphh

Everything a developer needs from Glyphh, in one repository: the plugin for Claude Code, and the SDKs your own
software calls Ada with.

| | Install | What it is |
|---|---|---|
| [`plugins/glyphh`](plugins/glyphh) | `/plugin install glyphh@glyphh` | The Glyphh plugin for Claude Code: your account, the Ada skill and the file ledger |
| [`sdk/python`](sdk/python) | `pip install glyphh` | Ada for Python: `from glyphh import Ada` |
| [`sdk/typescript`](sdk/typescript) | `npm i @glyphh-ai/glyphh` | Ada for TypeScript and JavaScript: `import { Ada } from "@glyphh-ai/glyphh"` |
| [`contract`](contract) | | The JSON Schema of a run's `Result` and of an Ada model's answers, and the fixtures both SDKs are tested against |

An Ada model is a typed spec and a precedent store that lives in your own Glyphh runtime, deployed by commit. A new
case is answered from the precedents closest to it: deterministically, with the precedents it stands on, and saying
when it does not know. The runtime is yours, hosted by Glyphh at `https://<machine>.glyphh.app` or self-hosted at
`https://<host>`; nothing of Glyphh's is between your app (or Claude) and it.

- **The platform**, to sign in, start a runtime and make its keys: https://platform.glyphh.ai
- **Self-hosting** a runtime (Docker Compose, Helm, Terraform): https://github.com/glyphh-ai/rrotor/tree/main/docs/self-hosting
- **Pricing**: https://glyphh.ai/pricing. Ada is in every plan, Free included; Glyphh never charges per seat, per
  model or per install, and local and self-hosted runtimes are unlimited.

## The plugin, in Claude Code

```
/plugin marketplace add glyphh-ai/glyphh
/plugin install glyphh@glyphh
```

One plugin, `glyphh`:

- **The account:** `/glyphh` opens the account, org, plan and billing panels; *"sign in to Glyphh"* gives the sign-in
  card in the chat.
- **Ada:** a skill. Ask Claude to build a model with you ("route these tickets the way we did before"): it writes the
  spec, deploys a commit and calls the model through your runtime's connector, `https://<machine>.glyphh.app/mcp` or
  `https://<host>/mcp`, added once in Claude's Connectors with one Allow click.
- **The file ledger:** what Claude last changed in each file and why, kept on your machine and handed back when
  Claude reads the file again.

The account panel is a mod (function hooks, early access in Claude Code 2.1): set
`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`. The skill and the ledger work without it. Details:
[`plugins/glyphh/README.md`](plugins/glyphh/README.md).

## The SDKs, in your software

Two settings: your runtime's address and a runtime key, `GLYPHH_RUNTIME_URL` and `GLYPHH_RUNTIME_KEY`.

```python
from glyphh import Ada

incidents = Ada().model("incidents")
r = incidents.decide({"error": {"what": {"class": "TimeoutError", "message": "payment gateway timed out", "status": 504}}})
if r.status == "done":
    apply(r.data["fix"])
```

```ts
import { Ada } from "@glyphh-ai/glyphh";

const incidents = new Ada().model("incidents");
const r = await incidents.decide({ error: { what: { class: "TimeoutError", message: "payment gateway timed out", status: 504 } } });
if (r.status === "done") apply(r.data.fix);
else if (r.status === "needs_input") await incidents.resume(r.run_id, await askSomeone(r.prompt));
```

A call is `POST /v1/runs` `{model, function, inputs, version?, clearance?}` at the runtime's address with
`Authorization: Bearer <runtime key>`, answered with the first `Result` (`run_id`, `status`, `data`, `step`,
`prompt`, `seconds`). See each SDK's README, and [`sdk/CHANGELOG.md`](sdk/CHANGELOG.md).

### New names in 3.0.0

The SDKs were `glyphh-ada` (PyPI) and `@glyphh-ai/ada` (npm), in `glyphh-ai/ada`. Both are
removed from the registries; the packages are now `glyphh` and `@glyphh-ai/glyphh`, here, with the same API: change the install and the import
(`from glyphh_ada import Ada` becomes `from glyphh import Ada`).

They start at **3.0.0** because the PyPI name `glyphh` was already Glyphh's: up to 2.6.7 it is the old HDC runtime
(`glyphh-runtime`), a different library. The major version marks the break: code written for `glyphh` 2.x does not
run on 3.x, and anything pinned to `glyphh<3` keeps the old library.

## Develop

```bash
CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1 claude plugin test plugins/glyphh
CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1 claude plugin validate --strict plugins/glyphh
(cd sdk/typescript && npm ci && npm test)
(cd sdk/python && pip install '.[dev]' && pytest -q)
```

CI (`.github/workflows`): `plugins.yml` and `sdks.yml` on every push and pull request; `publish.yml` publishes both
SDKs on a tag `sdk-v<version>`, the version both packages carry.

## License

Two licences, by folder (`LICENSE`): the plugin (`plugins/`) is under Glyphh's terms, for use by people who install
it from this marketplace; the SDKs (`sdk/`) and `contract/` are MIT.
