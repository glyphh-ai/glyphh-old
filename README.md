# Glyphh

Glyphh's developer surface: the Claude Code plugin, the SDKs and the contract they share.

| Folder | Install | What |
|---|---|---|
| [`plugins/glyphh`](plugins/glyphh) | `/plugin marketplace add glyphh-ai/glyphh`, then `/plugin install glyphh@glyphh` | The plugin: your Glyphh account in Claude Code, the Ada skill, the file ledger |
| [`sdk/python`](sdk/python) | `pip install glyphh` | Ada for Python, `from glyphh import Ada` |
| [`sdk/typescript`](sdk/typescript) | `npm i @glyphh-ai/glyphh` | Ada for TypeScript and JavaScript, `import { Ada } from "@glyphh-ai/glyphh"` |
| [`deploy`](deploy) | `curl -fsSL https://glyphh.ai/install.sh \| sh`, the chart's release, or a `git::` Terraform source (https://docs.glyphh.ai/run-rrotor) | Self-hosting rrotor, the runtime (image `ghcr.io/glyphh-ai/rrotor`): the source of the installer's Docker files, the Helm chart and the Terraform modules for AWS and GCP |
| [`benchmarks`](benchmarks) | | Ada against Claude and classic models on public data (Banking77, German Credit), with the results, the judges' prompts and the scripts |
| [`contract`](contract) | | JSON Schema of a run's `Result`, an Ada query's `Answer`, a capped `record`'s data and an error, a cluster's headers and codes, with the fixtures both SDKs are tested against |

An Ada model is a typed spec and a precedent store in your own Glyphh runtime, deployed by commit. A new case is
answered from the closest precedents: deterministically, with the precedents it stands on, and saying when it does
not know. The runtime is reached directly: hosted by Glyphh at `https://<machine>.glyphh.app`, or self-hosted at
`https://<host>`. Claude connects to its `/mcp`; your software calls its REST API with a runtime key.

- Platform (sign in, machines, runtime keys): https://platform.glyphh.ai
- Self-hosting (Docker, Helm, Terraform): https://docs.glyphh.ai/run-rrotor, built from the files in [`deploy/`](deploy)
- Benchmarks (Ada against Claude and classic models, on public data): [`benchmarks/`](benchmarks)
- Pricing: https://glyphh.ai/pricing. Ada is in every plan, Free included; self-hosting is free, at Community's limits without a licence key (one node,
  5,000 precedents).

## The runtime's REST API

What the SDKs call, at the runtime's address with `Authorization: Bearer <runtime key>`:

| Route | Does |
|---|---|
| `GET /v1/models` | The models: versions, the active one, its functions |
| `POST /v1/models/deploy` `{repo, commit, token?}` | A commit of a model's GitHub repo as its next version |
| `POST /v1/runs` `{model, function?, inputs?, version?, clearance?}` | Run a function (`start` by default): the first `Result` |
| `POST /v1/runs/{id}/continue` `{answer}` | Answer a run that waits (`needs_input`, `needs_approval`) |
| `POST /v1/runs/{id}/cancel` | Stop a run |
| `GET /v1/runs/{id}`, `GET /v1/runs/{id}/log` | A run and its last result; its log lines |
| `GET /v1/approvals` | The runs waiting for an approval |

A `Result` is `{run_id, model, version, function, status, data, step, prompt, seconds}` (`contract/contract.json`).

## Develop

```bash
CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1 claude plugin validate --strict plugins/glyphh
CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1 claude plugin test plugins/glyphh
(cd plugins/glyphh && node --test mcp/test/*.test.*)
(cd sdk/typescript && npm ci && npm test)
(cd sdk/python && python -m pip install '.[dev]' && python -m pytest -q)
```

CI (`.github/workflows`): `plugins.yml` and `sdks.yml` on every push and pull request; `publish.yml` publishes both
SDKs to PyPI and npm on a tag `sdk-v<version>`, the version both packages carry ([`sdk/CHANGELOG.md`](sdk/CHANGELOG.md));
`chart.yml` releases the Helm chart as `rrotor-chart-<version>` when `Chart.yaml`'s version is new.

## License

By folder (`LICENSE`): `plugins/` under Glyphh's terms; `sdk/`, `contract/`, `deploy/` and `benchmarks/` MIT. The
rrotor image the deploy files run is not covered by them; the benchmarks' data sets keep their own licences (CC BY 4.0).
