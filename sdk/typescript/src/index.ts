/**
 * @glyphh-ai/glyphh — your runtime, for one key. Every call is one request to the runtime's API at its own address
 * (https://<machine>.glyphh.app hosted, or https://<host> self-hosted), with a runtime key as the bearer. Nothing of Glyphh's is in between.
 *
 *     const incidents = new Ada().model("incidents");   // GLYPHH_RUNTIME_URL and GLYPHH_RUNTIME_KEY
 *     const r = await incidents.decide({ error: { ... } });
 *     if (r.status === "done") apply(r.data.fix);
 *     else if (r.status === "needs_input") await incidents.resume(r.run_id, await ask(r.prompt));
 */

export type Status = "done" | "needs_input" | "needs_approval" | "failed" | "expired" | "cancelled";

/** What a run answered: its status, and its data (the function's answer when done; why, when failed). */
export interface Result<T = unknown> {
  run_id: string;
  model: string;
  version: number;
  function: string;
  status: Status;
  data: T;
  step: string | null;
  prompt: string | null;
  seconds: number;
  /** Done, but indexed nothing: the store is at the licence's precedent cap (`data` has `message`, `precedents`, `cap`). */
  limit_exceeded: boolean;
}

/** What an Ada model's `query` answers. Trust `top` when `sufficient` and `confidence` clears your bar. */
export interface Answer {
  sufficient: boolean;
  confidence: number;
  support: number;
  count: number;
  top: string | null;
  outcomes: Record<string, number>;
  receipts: { id: string; sim: number; outcome: string | null; hash: string; author: string | null }[];
}

export interface ModelInfo {
  name: string;
  [key: string]: unknown;
}

/**
 * Sends one request; give your own to use another HTTP client. Answer the headers for Retry-After and read-your-writes
 * in a cluster.
 */
export type Transport = (
  method: string,
  url: string,
  headers: Record<string, string>,
  body?: string,
) => Promise<{ status: number; body: string; headers?: Record<string, string> }>;

/** How long, in seconds, a call keeps retrying (E_NO_HEAD; a read that could not reach the runtime) before it throws. */
export const RETRY_DEADLINE = 30;
/** An Ada model's functions that only read: safe to send again when the runtime could not be reached. */
export const READS: readonly string[] = ["query", "facts", "probabilities"];
const CLUSTER_SEQ = "rrotor-cluster-seq";
const MIN_SEQ = "rrotor-min-seq";

export interface AdaOptions {
  /** The runtime's address; else GLYPHH_RUNTIME_URL. */
  url?: string;
  /** A runtime key; else GLYPHH_RUNTIME_KEY. */
  key?: string;
  transport?: Transport;
  /** Seconds a call keeps retrying E_NO_HEAD, and a read that could not reach the runtime; 0: never. Default 30. */
  retryDeadline?: number;
  /** Send the highest `Rrotor-Cluster-Seq` seen as `Rrotor-Min-Seq`, so reads see this client's writes. Default true. */
  readYourWrites?: boolean;
  /** @internal The tests' clock: seconds now, and a wait of so many seconds. */
  clock?: { now(): number; sleep(seconds: number): Promise<void> };
}

export class AdaError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status = 0,
    readonly detail: Record<string, unknown> = {},
    /** Seconds, when the runtime said when to ask again (Retry-After). */
    readonly retryAfter?: number,
  ) {
    super(message);
    this.name = "AdaError";
  }
}

/** E_NO_HEAD (503): the cluster has no head, so it takes no writes; reads go on. Thrown once retries are spent. */
export class NoHeadError extends AdaError {
  override name = "NoHeadError";
}

/** E_HEAD_LOST (503): the head went while it had the write, which may or may not have been applied: never sent again by the client. */
export class HeadLostError extends AdaError {
  override name = "HeadLostError";
}

/** E_NOT_COMMITTED (503): most voters do not hold the write yet. It is kept, and committed when they come back: do not send it again. */
export class NotCommittedError extends AdaError {
  override name = "NotCommittedError";
}

/** E_RUN_LOST (410): the node that held the run is no longer in the cluster; the run is gone. */
export class RunLostError extends AdaError {
  override name = "RunLostError";
}

/**
 * E_READ_ONLY: a function marked `"writes": false` wrote, on a cluster's follower; the store is untouched. Mark it
 * `"writes": true` in the model's glyphh.json. `detail` has the run's `run_id` and `function`.
 */
export class ReadOnlyError extends AdaError {
  override name = "ReadOnlyError";
}

const TYPED: Record<string, typeof AdaError> = {
  E_NO_HEAD: NoHeadError,
  E_HEAD_LOST: HeadLostError,
  E_NOT_COMMITTED: NotCommittedError,
  E_RUN_LOST: RunLostError,
  E_READ_ONLY: ReadOnlyError,
};

const BY_STATUS: Record<number, string> = { 401: "E_AUTH", 402: "E_LIMIT", 404: "E_NOT_FOUND" };

/** Retry-After as seconds: a number of them, or an HTTP date. */
export function retryAfter(value: string | undefined): number | undefined {
  if (!value) return undefined;
  const n = Number(value);
  if (value.trim() !== "" && Number.isFinite(n)) return Math.max(0, n);
  const at = Date.parse(value);
  return Number.isNaN(at) ? undefined : Math.max(0, (at - Date.now()) / 1000);
}

/**
 * E_NO_HEAD, any call: refused before it was forwarded, so nothing ran. A read, also when the runtime could not be
 * reached or a proxy in front of it answered 502, 503 or 504. A write that may have been applied (E_UNREACHABLE,
 * E_HEAD_LOST, E_NOT_COMMITTED) is never sent again.
 */
function retryable(err: AdaError, read: boolean): boolean {
  if (err.code === "E_NO_HEAD") return true;
  return read && (err.code === "E_UNREACHABLE" || (err.code === "E_RUNTIME" && [502, 503, 504].includes(err.status)));
}

function asResult<T>(body: Omit<Result<T>, "limit_exceeded">): Result<T> {
  const data = body.data as { status?: unknown; code?: unknown; reason?: unknown } | null;
  const isObject = typeof data === "object" && data !== null;
  if (body.status === "failed" && isObject && data.code === "E_READ_ONLY") {
    const reason = typeof data.reason === "string" ? data.reason : `${body.function} wrote, and it is marked read-only`;
    throw new ReadOnlyError("E_READ_ONLY", reason, 200, { run_id: body.run_id, function: body.function });
  }
  return { ...body, limit_exceeded: body.status === "done" && isObject && data.status === "limit_exceeded" };
}

const realClock = {
  now: () => performance.now() / 1000,
  sleep: (seconds: number) => new Promise<void>((resolve) => setTimeout(resolve, seconds * 1000)),
};

function env(name: string): string | undefined {
  const p = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process;
  return p?.env?.[name];
}

const fetchTransport: Transport = async (method, url, headers, body) => {
  const res = await fetch(url, body === undefined ? { method, headers } : { method, headers, body });
  const answered: Record<string, string> = {};
  res.headers.forEach((value, name) => (answered[name] = value));
  return { status: res.status, body: await res.text(), headers: answered };
};

/**
 * In a cluster: E_NO_HEAD, and a read that could not reach the runtime, are retried with backoff (Retry-After
 * honoured) for up to `retryDeadline` seconds; the highest `Rrotor-Cluster-Seq` answered is sent back as
 * `Rrotor-Min-Seq`, so a read sees this client's writes on whichever node answers it.
 */
export class Ada {
  readonly url: string;
  readonly retryDeadline: number;
  readonly readYourWrites: boolean;
  readonly #key: string;
  readonly #send: Transport;
  readonly #clock: { now(): number; sleep(seconds: number): Promise<void> };
  #seq = 0;

  constructor(options: AdaOptions = {}) {
    this.url = (options.url ?? env("GLYPHH_RUNTIME_URL") ?? "").replace(/\/+$/, "");
    this.#key = options.key ?? env("GLYPHH_RUNTIME_KEY") ?? "";
    if (!this.url || !this.#key) {
      throw new AdaError("E_CONFIG", "the runtime's address and a runtime key are needed: GLYPHH_RUNTIME_URL, GLYPHH_RUNTIME_KEY");
    }
    this.#send = options.transport ?? fetchTransport;
    this.retryDeadline = options.retryDeadline ?? RETRY_DEADLINE;
    this.readYourWrites = options.readYourWrites ?? true;
    this.#clock = options.clock ?? realClock;
  }

  /** The highest `Rrotor-Cluster-Seq` the runtime has answered this client (0: none, or not a cluster). */
  get clusterSeq(): number {
    return this.#seq;
  }

  /**
   * One request, sent again while it may be and the deadline allows. `read`: safe to send again when it could not
   * reach the runtime; a GET by default.
   */
  async call<T = unknown>(method: string, path: string, body?: unknown, read = method === "GET"): Promise<T> {
    const raw = body === undefined ? undefined : JSON.stringify(body);
    const deadline = this.#clock.now() + this.retryDeadline;
    for (let attempt = 0; ; attempt++) {
      try {
        return await this.#once<T>(method, path, raw);
      } catch (e) {
        if (!(e instanceof AdaError) || !retryable(e, read)) throw e;
        // Retry-After, else 0.25 s doubling to 2 s, jittered by up to half
        const wait = e.retryAfter ?? Math.min(2, 0.25 * 2 ** attempt) * (0.5 + Math.random() / 2);
        if (this.#clock.now() + wait > deadline) throw e;
        await this.#clock.sleep(wait);
      }
    }
  }

  async #once<T>(method: string, path: string, raw: string | undefined): Promise<T> {
    const headers: Record<string, string> = { authorization: `Bearer ${this.#key}`, accept: "application/json" };
    if (raw !== undefined) headers["content-type"] = "application/json";
    if (this.readYourWrites && this.#seq) headers[MIN_SEQ] = String(this.#seq);
    let status: number;
    let text: string;
    let answered: Record<string, string> | undefined;
    try {
      ({ status, body: text, headers: answered } = await this.#send(method, `${this.url}${path}`, headers, raw));
    } catch (e) {
      throw new AdaError("E_UNREACHABLE", `the runtime could not be reached: ${(e as Error).message}`);
    }
    const got: Record<string, string> = {};
    for (const [k, v] of Object.entries(answered ?? {})) got[k.toLowerCase()] = String(v);
    const seq = Number(got[CLUSTER_SEQ]);
    if (Number.isInteger(seq) && seq > this.#seq) this.#seq = seq;
    let parsed: unknown = {};
    try {
      parsed = text ? JSON.parse(text) : {};
    } catch {
      parsed = {};
    }
    if (status >= 400) {
      const err = ((parsed as { error?: Record<string, unknown> }).error ?? {}) as Record<string, unknown>;
      const { code, message, ...detail } = err;
      const named = (code as string | undefined) ?? BY_STATUS[status] ?? "E_RUNTIME";
      throw new (TYPED[named] ?? AdaError)(
        named,
        (message as string | undefined) ?? `the runtime answered ${status}`,
        status,
        detail,
        retryAfter(got["retry-after"]),
      );
    }
    return parsed as T;
  }

  /** The models deployed: each one's versions, the active one and its functions. */
  async models(): Promise<ModelInfo[]> {
    return (await this.call<{ models: ModelInfo[] }>("GET", "/v1/models")).models;
  }

  /** A commit of a model's GitHub repo (owner/name) as its next version; a token for a private repo. */
  deploy(repo: string, commit: string, token?: string): Promise<{ model: string; version: number; commit_sha: string }> {
    return this.call("POST", "/v1/models/deploy", token === undefined ? { repo, commit } : { repo, commit, token });
  }

  model(name: string): AdaModel {
    return new AdaModel(this, name);
  }

  /** A run as the runtime shows it: status, function, times, the last Result. */
  run(runId: string): Promise<Record<string, unknown>> {
    return this.call("GET", `/v1/runs/${encodeURIComponent(runId)}`);
  }

  async log(runId: string): Promise<unknown[]> {
    return (await this.call<{ lines: unknown[] }>("GET", `/v1/runs/${encodeURIComponent(runId)}/log`)).lines;
  }

  /** Answer a run that waits (`needs_input`, `needs_approval`): the next Result. */
  async resume<T = unknown>(runId: string, answer: unknown): Promise<Result<T>> {
    return asResult(await this.call("POST", `/v1/runs/${encodeURIComponent(runId)}/continue`, { answer }));
  }

  async cancel<T = unknown>(runId: string): Promise<Result<T>> {
    return asResult(await this.call("POST", `/v1/runs/${encodeURIComponent(runId)}/cancel`, {}));
  }
}

export interface CallOptions {
  version?: number;
  /** Who asks, 0 to 1: the model's secured layers are cut from the answer below their weight. */
  clearance?: number;
}

/** One model on the runtime. `call` reaches any function; the named ones are an Ada model's own. */
export class AdaModel {
  constructor(
    readonly ada: Ada,
    readonly name: string,
  ) {}

  async call<T = unknown>(fn = "start", inputs: Record<string, unknown> = {}, options: CallOptions = {}): Promise<Result<T>> {
    const body: Record<string, unknown> = { model: this.name, function: fn, inputs };
    if (options.version !== undefined) body.version = options.version;
    if (options.clearance !== undefined) body.clearance = options.clearance;
    return asResult(await this.ada.call("POST", "/v1/runs", body, READS.includes(fn)));
  }

  resume<T = unknown>(runId: string, answer: unknown): Promise<Result<T>> {
    return this.ada.resume(runId, answer);
  }

  record(data: Record<string, unknown>, outcome?: string): Promise<Result<{ id: string }>> {
    return this.call("record", outcome === undefined ? { data } : { data, outcome });
  }

  query(data: Record<string, unknown>, options: CallOptions = {}): Promise<Result<Answer>> {
    return this.call("query", { data }, options);
  }

  facts(data: Record<string, unknown>, options: CallOptions & { top?: number } = {}): Promise<Result<unknown[]>> {
    const { top, ...rest } = options;
    return this.call("facts", top === undefined ? { data } : { data, top }, rest);
  }

  probabilities(data: Record<string, unknown>, options: CallOptions = {}): Promise<Result<Record<string, number>>> {
    return this.call("probabilities", { data }, options);
  }

  decide<T = unknown>(data: Record<string, unknown>, options: CallOptions = {}): Promise<Result<T>> {
    return this.call("decide", { data }, options);
  }

  /** The model weighs its roles from its own precedents and calibrates; `sample` is how many of the newest to calibrate on. */
  learn(options: CallOptions & { sample?: number } = {}): Promise<Result<{ roles: Record<string, number>; tau: number; precedents: number }>> {
    const { sample, ...rest } = options;
    return this.call("learn", sample === undefined ? {} : { sample }, rest);
  }
}
