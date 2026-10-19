// The client against the contract's fixtures: every request as the runtime expects it, every answer read right,
// every refusal an AdaError with the runtime's code.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { Ada, AdaError, NoHeadError, NotCommittedError, ReadOnlyError, RunLostError, retryAfter } from "../dist/index.js";

const fixtures = JSON.parse(readFileSync(new URL("../../../contract/fixtures.json", import.meta.url), "utf8"));
const byName = (name) => fixtures.cases.find((c) => c.name === name);
const answered = (response) => [response.status, response.body, response.headers ?? {}];

/** No real waiting: the client's sleeps recorded, its clock moved by them. */
function fakeClock() {
  const slept = [];
  let now = 0;
  return { slept, clock: { now: () => now, sleep: async (s) => { slept.push(s); now += s; } } };
}

/** A runtime that answers from a script of [status, body] or [status, body, headers]; an Error is thrown. */
function fake(...answers) {
  const options = answers.length && !Array.isArray(answers.at(-1)) && !(answers.at(-1) instanceof Error) ? answers.pop() : {};
  const calls = [];
  const transport = async (method, url, headers, body) => {
    calls.push({ method, url, headers, body: body === undefined ? undefined : JSON.parse(body) });
    const next = answers.shift();
    if (next instanceof Error) throw next;
    const [status, answer, got] = next;
    return got === undefined ? { status, body: JSON.stringify(answer) } : { status, body: JSON.stringify(answer), headers: got };
  };
  return { ada: new Ada({ url: "https://m1.glyphh.app/", key: "glyphh_rk_test", transport, ...options }), calls };
}

test("a decide that is done, with a clearance", async () => {
  const c = byName("a call that is done");
  const { ada, calls } = fake([200, c.response.body]);
  const r = await ada.model("incidents").decide(c.request.body.inputs.data, { clearance: 0.5 });
  assert.equal(r.status, "done");
  assert.equal(r.data.fix, "raise circuit breaker");
  assert.deepEqual(calls[0].body, c.request.body);
  assert.equal(calls[0].url, "https://m1.glyphh.app/v1/runs");
  assert.equal(calls[0].headers.authorization, "Bearer glyphh_rk_test");
});

test("a run that needs input is resumed", async () => {
  const c = byName("a call that needs input, then continued");
  const { ada, calls } = fake([200, c.response.body], [200, c.then.response.body]);
  const m = ada.model("incidents");
  const r = await m.decide(c.request.body.inputs.data);
  assert.equal(r.status, "needs_input");
  const done = await m.resume(r.run_id, "rotate certificate");
  assert.equal(done.data.fix, "rotate certificate");
  assert.equal(calls[1].url, "https://m1.glyphh.app/v1/runs/9b0d44/continue");
  assert.deepEqual(calls[1].body, { answer: "rotate certificate" });
});

test("a query, and the other functions name themselves", async () => {
  const c = byName("a query");
  const { ada, calls } = fake(...Array(7).fill([200, c.response.body]));
  const m = ada.model("incidents");
  const r = await m.query(c.request.body.inputs.data);
  assert.equal(r.data.top, "rotate certificate");
  await m.record({ a: 1 }, "fixed");
  await m.record({ a: 1 });
  await m.facts({ a: 1 }, { top: 2, clearance: 0.5 });
  await m.probabilities({ a: 1 });
  await m.learn();
  await m.learn({ sample: 50, clearance: 0.5 });
  assert.deepEqual(
    calls.map((k) => [k.body.function, k.body.inputs, k.body.clearance]),
    [
      ["query", { data: c.request.body.inputs.data }, undefined],
      ["record", { data: { a: 1 }, outcome: "fixed" }, undefined],
      ["record", { data: { a: 1 } }, undefined],
      ["facts", { data: { a: 1 }, top: 2 }, 0.5],
      ["probabilities", { data: { a: 1 } }, undefined],
      ["learn", {}, undefined],
      ["learn", { sample: 50 }, 0.5],
    ],
  );
});

for (const name of ["a wrong key", "a paused runtime", "a model that is not there"]) {
  test(`a refusal is an AdaError: ${name}`, async () => {
    const c = byName(name);
    const { ada } = fake([c.response.status, c.response.body]);
    await assert.rejects(ada.model(c.request.body.model).call("start"), (e) => {
      assert.ok(e instanceof AdaError);
      assert.equal(e.code, c.response.body.error.code);
      assert.equal(e.status, c.response.status);
      assert.equal(e.message, c.response.body.error.message);
      if (name === "a paused runtime") assert.deepEqual(e.detail, { limit: "runtime_hours" });
      return true;
    });
  });
}

test("the runtime and the rest of the api", async () => {
  const models = { models: [{ name: "incidents", active: 1 }] };
  const { ada, calls } = fake([200, models], [201, { model: "incidents", version: 2, commit_sha: "a".repeat(40) }], [200, { id: "r1" }], [200, { lines: [1] }], [200, byName("a call that is done").response.body]);
  assert.deepEqual(await ada.models(), models.models);
  assert.equal((await ada.deploy("octo/incidents", "a".repeat(40), "ghp_x")).version, 2);
  assert.deepEqual(await ada.run("r1"), { id: "r1" });
  assert.deepEqual(await ada.log("r1"), [1]);
  assert.equal((await ada.cancel("r1")).status, "done");
  assert.deepEqual(
    calls.map((k) => [k.method, k.url.replace("https://m1.glyphh.app", "")]),
    [["GET", "/v1/models"], ["POST", "/v1/models/deploy"], ["GET", "/v1/runs/r1"], ["GET", "/v1/runs/r1/log"], ["POST", "/v1/runs/r1/cancel"]],
  );
  assert.deepEqual(calls[1].body, { repo: "octo/incidents", commit: "a".repeat(40), token: "ghp_x" });
  assert.equal(calls[0].body, undefined);
});

test("an answer that is not json, no code, and a runtime that cannot be reached", async () => {
  const broken = new Ada({ url: "https://m1.glyphh.app", key: "k", retryDeadline: 0, transport: async () => ({ status: 502, body: "<html>" }) });
  await assert.rejects(broken.models(), (e) => e.code === "E_RUNTIME" && e.status === 502);
  const gone = new Ada({ url: "https://m1.glyphh.app", key: "k", retryDeadline: 0, transport: async () => { throw new Error("no route"); } });
  await assert.rejects(gone.models(), (e) => e.code === "E_UNREACHABLE");
  for (const [status, code] of [[401, "E_AUTH"], [402, "E_LIMIT"], [404, "E_NOT_FOUND"]]) {
    const a = new Ada({ url: "https://m1.glyphh.app", key: "k", transport: async () => ({ status, body: "{}" }) });
    await assert.rejects(a.models(), (e) => e.code === code);
  }
});

test("the address and key are needed", () => {
  delete process.env.GLYPHH_RUNTIME_URL;
  delete process.env.GLYPHH_RUNTIME_KEY;
  assert.throws(() => new Ada(), (e) => e.code === "E_CONFIG");
  process.env.GLYPHH_RUNTIME_URL = "https://m2.glyphh.app/";
  process.env.GLYPHH_RUNTIME_KEY = "glyphh_rk_env";
  assert.equal(new Ada().url, "https://m2.glyphh.app");
});

// A cluster (rrotor's docs/specs/cluster.md)

test("no head is retried as Retry-After says, and the seq is kept", async () => {
  const c = byName("a write while the cluster has no head, sent again");
  const { slept, clock } = fakeClock();
  const { ada, calls } = fake(answered(c.response), answered(c.response), answered(c.then.response), { clock });
  const r = await ada.model("incidents").record(c.request.body.inputs.data, "raise circuit breaker");
  assert.equal(r.status, "done");
  assert.deepEqual(r.data, { id: "a1b2c3" });
  assert.deepEqual(slept, [2, 2]);
  assert.deepEqual(calls.map((k) => k.body), [c.request.body, c.request.body, c.request.body]);
  assert.equal(ada.clusterSeq, 1042);
});

test("no head past the deadline is a NoHeadError", async () => {
  const c = byName("a write while the cluster has no head, sent again");
  const { slept, clock } = fakeClock();
  const { ada, calls } = fake(...Array(6).fill(answered(c.response)), { clock, retryDeadline: 9 });
  await assert.rejects(ada.model("incidents").record({ a: 1 }), (e) => {
    assert.ok(e instanceof NoHeadError && e instanceof AdaError);
    assert.deepEqual([e.code, e.status, e.retryAfter, e.name], ["E_NO_HEAD", 503, 2, "NoHeadError"]);
    return true;
  });
  assert.deepEqual(slept, [2, 2, 2, 2]);
  assert.equal(calls.length, 5);
  const once = fake(answered(c.response), { clock, retryDeadline: 0 });
  await assert.rejects(once.ada.model("incidents").record({ a: 1 }), NoHeadError);
  assert.equal(once.calls.length, 1);
});

test("a read is sent again when the runtime cannot be reached, and a write is not", async () => {
  const { slept, clock } = fakeClock();
  const q = fake(new Error("reset"), [502, {}], answered(byName("a query").response), { clock });
  assert.equal((await q.ada.model("incidents").query({ a: 1 })).data.top, "rotate certificate");
  assert.equal(q.calls.length, 3);
  assert.ok(slept.length === 2 && slept[0] >= 0.125 && slept[0] <= 0.25 && slept[1] >= 0.25 && slept[1] <= 0.5);
  const g = fake(new Error("reset"), [200, { models: [] }], { clock });
  assert.deepEqual(await g.ada.models(), []);
  const w = fake(new Error("reset"), { clock });
  await assert.rejects(w.ada.model("incidents").record({ a: 1 }), (e) => e.code === "E_UNREACHABLE");
  assert.equal(w.calls.length, 1);
  const resumed = fake(new Error("reset"), { clock });
  await assert.rejects(resumed.ada.resume("r1", "yes"));
  assert.equal(resumed.calls.length, 1);
});

test("read-your-writes sends the highest seq seen, or nothing when off", async () => {
  const c = byName("a read after a write, on another node");
  const { ada, calls } = fake(answered(c.response), answered(c.then.response), [200, { models: [] }, { "Rrotor-Cluster-Seq": "7" }]);
  const m = ada.model("incidents");
  await m.record(c.request.body.inputs.data, "raise circuit breaker");
  assert.equal(calls[0].headers["rrotor-min-seq"], undefined);
  const r = await m.query(c.then.request.body.inputs.data);
  assert.equal(r.data.top, "raise circuit breaker");
  assert.equal(calls[1].headers["rrotor-min-seq"], c.then.request.headers["Rrotor-Min-Seq"]);
  await ada.models();
  assert.equal(ada.clusterSeq, 1042); // never lowered by a node further behind
  const off = fake(answered(c.response), answered(c.then.response), { readYourWrites: false });
  await off.ada.model("incidents").record({ a: 1 });
  await off.ada.model("incidents").query({ a: 1 });
  assert.equal(off.calls[1].headers["rrotor-min-seq"], undefined);
  assert.equal(off.ada.clusterSeq, 1042);
});

for (const [name, error] of [["a write most voters do not hold yet", NotCommittedError], ["a run on a node that left the cluster", RunLostError]]) {
  test(`a cluster's refusal is typed and not sent again: ${name}`, async () => {
    const c = byName(name);
    const { slept, clock } = fakeClock();
    const { ada, calls } = fake(answered(c.response), { clock });
    const call = c.request.path === "/v1/runs" ? ada.model("incidents").record({ a: 1 }) : ada.resume("rrotor-2~9b0d", "rotate certificate");
    await assert.rejects(call, (e) => {
      assert.ok(e instanceof error && e instanceof AdaError);
      assert.deepEqual([e.code, e.status], [c.response.body.error.code, c.response.status]);
      return true;
    });
    assert.equal(calls.length, 1);
    assert.deepEqual(slept, []);
  });
}

test("a reading function that wrote is a ReadOnlyError", async () => {
  const c = byName("a reading function that wrote, on a follower");
  const { ada } = fake(answered(c.response));
  await assert.rejects(ada.model("incidents").query({ a: 1 }), (e) => {
    assert.ok(e instanceof ReadOnlyError);
    assert.equal(e.code, "E_READ_ONLY");
    assert.match(e.message, /writes/);
    assert.deepEqual(e.detail, { run_id: "rrotor-1~c3", function: "query" });
    return true;
  });
});

test("a record past the cap is done and says limit_exceeded", async () => {
  const c = byName("a record past the precedent cap");
  const { ada } = fake(answered(c.response), answered(byName("a call that is done").response));
  const r = await ada.model("incidents").record({ a: 1 });
  assert.equal(r.status, "done");
  assert.equal(r.limit_exceeded, true);
  assert.equal(r.data.cap, 50000);
  assert.equal((await ada.model("incidents").decide({ a: 1 })).limit_exceeded, false);
});

test("Retry-After as a date, and a transport that answers no headers", async () => {
  assert.equal(retryAfter("Wed, 21 Oct 2015 07:28:00 GMT"), 0);
  assert.equal(retryAfter("1.5"), 1.5);
  assert.equal(retryAfter("soon"), undefined);
  const { ada } = fake([200, { models: [] }]);
  assert.deepEqual(await ada.models(), []);
  assert.equal(ada.clusterSeq, 0);
});
