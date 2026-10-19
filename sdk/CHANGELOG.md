# The SDKs' changelog

Both packages carry one version; a tag `sdk-v<version>` publishes both.

## 3.1.0

For a clustered self-hosted runtime (rrotor's [cluster spec](https://github.com/glyphh-ai/rrotor/blob/main/docs/specs/cluster.md)):

- `E_NO_HEAD` (503, no head: writes wait, reads go on) is retried with backoff, `Retry-After` honoured; so is a read
  (a GET; `query`, `facts`, `probabilities`) the runtime could not answer (unreachable, or a proxy's 502, 503, 504).
  A write that may have been applied is never sent again. `retry_deadline` / `retryDeadline` (seconds, default 30;
  0: never retry).
- Read-your-writes: the highest `Rrotor-Cluster-Seq` answered is sent as `Rrotor-Min-Seq` on later calls, so a
  read sees the client's writes on whichever node answers it. `read_your_writes=False` / `readYourWrites: false`
  turns it off; `cluster_seq` / `clusterSeq` shows it.
- Typed errors, each an `AdaError`: `NoHeadError`, `NotCommittedError` (the write is kept: do not resend it),
  `RunLostError` (410), `ReadOnlyError` (a function marked `"writes": false` wrote on a follower; raised from the
  `failed` run).
- `result.limit_exceeded`: a `done` run that indexed nothing, the store at the licence key's precedent cap.
- A transport may answer headers: `(status, body, headers)` in Python, `{status, body, headers}` in TypeScript.

## 3.0.0

- The packages are `glyphh` on PyPI (`from glyphh import Ada`) and `@glyphh-ai/glyphh` on npm, from this repository.
  The API is that of `glyphh-ada` and `@glyphh-ai/ada` 0.4.0: change the install and the import.
- A major version on purpose: `glyphh` up to 2.6.7 on PyPI is a different, older library. Code for 2.x does not run on
  3.x; anything pinned to `glyphh<3` keeps the old one.
- A runtime's address may be self-hosted, `https://<host>`, as well as `https://<machine>.glyphh.app`.

## 0.4.0

`learn()`.
