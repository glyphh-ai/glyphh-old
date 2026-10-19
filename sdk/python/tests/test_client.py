"""The client against the contract's fixtures: every request as the runtime expects it, every answer read right,
every refusal an AdaError with the runtime's code."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import validate

import glyphh.client
from glyphh import (
    Ada,
    AdaError,
    NoHeadError,
    NotCommittedError,
    ReadOnlyError,
    Result,
    RunLostError,
)

CONTRACT = json.loads((Path(__file__).parents[3] / "contract" / "contract.json").read_text())
FIXTURES = json.loads((Path(__file__).parents[3] / "contract" / "fixtures.json").read_text())


class Fake:
    """A runtime that answers from a script of (status, body) or (status, body, headers); an exception is raised."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, dict(headers), json.loads(body) if body else None))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        status, content, *got = answer
        return (status, json.dumps(content).encode(), *got)


def case(name):
    return next(c for c in FIXTURES["cases"] if c["name"] == name)


def ada(*answers, **options):
    fake = Fake(*answers)
    return Ada("https://m1.glyphh.app/", "glyphh_rk_test", transport=fake, **options), fake


def answered(response):
    return (response["status"], response["body"], response.get("headers", {}))


@pytest.fixture
def clock(monkeypatch):
    """No real waiting: the client's sleeps recorded, its clock moved by them."""
    slept, now = [], [0.0]

    def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(glyphh.client, "_sleep", sleep)
    monkeypatch.setattr(glyphh.client, "_now", lambda: now[0])
    return slept


def test_a_decide_that_is_done_with_a_clearance():
    c = case("a call that is done")
    client, fake = ada((200, c["response"]["body"]))
    r = client.model("incidents").decide(c["request"]["body"]["inputs"]["data"], clearance=0.5)
    validate(c["response"]["body"], CONTRACT["result"])
    assert isinstance(r, Result) and r.done and not r.waiting and r.ended
    assert (r.run_id, r.data["fix"], r.seconds) == ("7e2a1c", "raise circuit breaker", 0.21)
    method, url, headers, body = fake.calls[0]
    assert (method, url) == ("POST", "https://m1.glyphh.app/v1/runs")
    assert headers["authorization"] == "Bearer glyphh_rk_test" and headers["content-type"] == "application/json"
    assert body == c["request"]["body"]


def test_a_run_that_needs_input_is_resumed():
    c = case("a call that needs input, then continued")
    client, fake = ada((200, c["response"]["body"]), (200, c["then"]["response"]["body"]))
    m = client.model("incidents")
    r = m.decide(c["request"]["body"]["inputs"]["data"])
    assert r.waiting and r.status == "needs_input" and "How was this one fixed" in r.prompt
    done = m.resume(r.run_id, "rotate certificate")
    assert done.done and done.data["fix"] == "rotate certificate" and done.data["recorded"]
    assert fake.calls[1][1] == "https://m1.glyphh.app/v1/runs/9b0d44/continue"
    assert fake.calls[1][3] == {"answer": "rotate certificate"}


def test_a_query_answers_the_contracts_answer_and_the_other_functions_name_themselves():
    c = case("a query")
    body = c["response"]["body"]
    client, fake = ada(*[(200, body)] * 7)
    m = client.model("incidents")
    r = m.query(c["request"]["body"]["inputs"]["data"])
    validate(r.data, CONTRACT["answer"])
    assert r.data["top"] == "rotate certificate" and r.data["sufficient"]
    m.record({"a": 1}, "fixed")
    m.record({"a": 1})
    m.facts({"a": 1}, top=2, clearance=0.5)
    m.probabilities({"a": 1})
    m.learn()
    m.learn(sample=50, clearance=0.5)
    sent = [(call[3]["function"], call[3]["inputs"], call[3].get("clearance")) for call in fake.calls]
    assert sent == [
        ("query", {"data": c["request"]["body"]["inputs"]["data"]}, None),
        ("record", {"data": {"a": 1}, "outcome": "fixed"}, None),
        ("record", {"data": {"a": 1}}, None),
        ("facts", {"data": {"a": 1}, "top": 2}, 0.5),
        ("probabilities", {"data": {"a": 1}}, None),
        ("learn", {}, None),
        ("learn", {"sample": 50}, 0.5),
    ]


@pytest.mark.parametrize("name", ["a wrong key", "a paused runtime", "a model that is not there"])
def test_a_refusal_is_an_ada_error_with_the_runtimes_code(name):
    c = case(name)
    client, _ = ada((c["response"]["status"], c["response"]["body"]))
    validate(c["response"]["body"], CONTRACT["error"])
    with pytest.raises(AdaError) as caught:
        client.model(c["request"]["body"]["model"]).call("start")
    err = caught.value
    assert (err.code, err.status) == (c["response"]["body"]["error"]["code"], c["response"]["status"])
    assert err.message == c["response"]["body"]["error"]["message"]
    if name == "a paused runtime":
        assert err.detail == {"limit": "runtime_hours"}
    assert repr(err).startswith("AdaError(")


def test_the_runtime_and_the_rest_of_the_api():
    models = {"models": [{"name": "incidents", "active": 1}]}
    run = {"id": "r1", "status": "done"}
    client, fake = ada((200, models), (201, {"model": "incidents", "version": 2, "commit_sha": "a" * 40}), (200, run), (200, {"lines": [1]}), (200, case("a call that is done")["response"]["body"]))
    assert client.models() == models["models"]
    assert client.deploy("octo/incidents", "a" * 40, "ghp_x")["version"] == 2
    assert client.run("r1") == run and client.log("r1") == [1]
    assert client.cancel("r1").done
    assert [(c[0], c[1].removeprefix("https://m1.glyphh.app")) for c in fake.calls] == [
        ("GET", "/v1/models"),
        ("POST", "/v1/models/deploy"),
        ("GET", "/v1/runs/r1"),
        ("GET", "/v1/runs/r1/log"),
        ("POST", "/v1/runs/r1/cancel"),
    ]
    assert fake.calls[1][3] == {"repo": "octo/incidents", "commit": "a" * 40, "token": "ghp_x"}
    assert fake.calls[0][3] is None and "content-type" not in fake.calls[0][2]


def test_an_answer_that_is_not_json_or_no_code_and_a_runtime_that_cannot_be_reached():
    def broken(method, url, headers, body):
        return 502, b"<html>bad gateway</html>"

    with pytest.raises(AdaError) as caught:
        Ada("https://m1.glyphh.app", "k", transport=broken, retry_deadline=0).models()
    assert (caught.value.code, caught.value.status) == ("E_RUNTIME", 502)

    def gone(method, url, headers, body):
        raise OSError("no route to host")

    with pytest.raises(AdaError) as caught:
        Ada("https://m1.glyphh.app", "k", transport=gone, retry_deadline=0).models()
    assert caught.value.code == "E_UNREACHABLE"
    for status, code in ((401, "E_AUTH"), (402, "E_LIMIT"), (404, "E_NOT_FOUND")):
        with pytest.raises(AdaError) as caught:
            Ada("https://m1.glyphh.app", "k", transport=lambda *a, s=status: (s, b"{}")).models()
        assert caught.value.code == code


def test_the_address_and_key_come_from_the_environment_or_are_refused(monkeypatch):
    monkeypatch.delenv("GLYPHH_RUNTIME_URL", raising=False)
    monkeypatch.delenv("GLYPHH_RUNTIME_KEY", raising=False)
    with pytest.raises(AdaError) as caught:
        Ada()
    assert caught.value.code == "E_CONFIG"
    monkeypatch.setenv("GLYPHH_RUNTIME_URL", "https://m2.glyphh.app/")
    monkeypatch.setenv("GLYPHH_RUNTIME_KEY", "glyphh_rk_env")
    assert Ada().url == "https://m2.glyphh.app"


# A cluster (rrotor's docs/specs/cluster.md)


def test_no_head_is_retried_as_retry_after_says_and_the_seq_is_kept(clock):
    c = case("a write while the cluster has no head, sent again")
    client, fake = ada(answered(c["response"]), answered(c["response"]), answered(c["then"]["response"]))
    r = client.model("incidents").record(c["request"]["body"]["inputs"]["data"], "raise circuit breaker")
    assert r.done and r.data == {"id": "a1b2c3"} and clock == [2.0, 2.0]
    assert [call[3] for call in fake.calls] == [c["request"]["body"]] * 3
    assert client.cluster_seq == 1042


def test_no_head_past_the_deadline_is_a_no_head_error(clock):
    c = case("a write while the cluster has no head, sent again")
    client, fake = ada(*[answered(c["response"])] * 6, retry_deadline=9)
    with pytest.raises(NoHeadError) as caught:
        client.model("incidents").record({"a": 1})
    assert (caught.value.code, caught.value.status, caught.value.retry_after) == ("E_NO_HEAD", 503, 2.0)
    assert clock == [2.0] * 4 and len(fake.calls) == 5
    client, fake = ada(answered(c["response"]), retry_deadline=0)
    with pytest.raises(NoHeadError):
        client.model("incidents").record({"a": 1})
    assert clock == [2.0] * 4 and len(fake.calls) == 1


def test_a_read_is_sent_again_when_the_runtime_cannot_be_reached_and_a_write_is_not(clock):
    q = case("a query")
    client, fake = ada(OSError("reset"), (502, {}), answered(q["response"]))
    assert client.model("incidents").query({"a": 1}).data["top"] == "rotate certificate"
    assert len(fake.calls) == 3 and len(clock) == 2 and 0.125 <= clock[0] <= 0.25 and 0.25 <= clock[1] <= 0.5
    client, fake = ada(OSError("reset"), (200, {"models": []}))
    assert client.models() == []
    client, fake = ada(OSError("reset"))
    with pytest.raises(AdaError) as caught:
        client.model("incidents").record({"a": 1})
    assert caught.value.code == "E_UNREACHABLE" and len(fake.calls) == 1
    client, fake = ada(OSError("reset"))
    with pytest.raises(AdaError):
        client.resume("r1", "yes")
    assert len(fake.calls) == 1


def test_read_your_writes_sends_the_highest_seq_seen_or_nothing_when_off():
    c = case("a read after a write, on another node")
    client, fake = ada(answered(c["response"]), answered(c["then"]["response"]), (200, {"models": []}, {"Rrotor-Cluster-Seq": "7"}))
    m = client.model("incidents")
    m.record(c["request"]["body"]["inputs"]["data"], "raise circuit breaker")
    assert "rrotor-min-seq" not in fake.calls[0][2]
    r = m.query(c["then"]["request"]["body"]["inputs"]["data"])
    validate(r.data, CONTRACT["answer"])
    assert fake.calls[1][2]["rrotor-min-seq"] == c["then"]["request"]["headers"]["Rrotor-Min-Seq"]
    client.models()
    assert client.cluster_seq == 1042  # never lowered by a node further behind
    client, fake = ada(answered(c["response"]), answered(c["then"]["response"]), read_your_writes=False)
    client.model("incidents").record({"a": 1})
    client.model("incidents").query({"a": 1})
    assert "rrotor-min-seq" not in fake.calls[1][2] and client.cluster_seq == 1042


@pytest.mark.parametrize(
    ("name", "error"),
    [("a write most voters do not hold yet", NotCommittedError), ("a run on a node that left the cluster", RunLostError)],
)
def test_a_clusters_refusals_are_typed_and_not_sent_again(clock, name, error):
    c = case(name)
    validate(c["response"]["body"], CONTRACT["error"])
    client, fake = ada(answered(c["response"]))
    with pytest.raises(error) as caught:
        if c["request"]["path"] == "/v1/runs":
            client.model("incidents").record({"a": 1})
        else:
            client.resume("rrotor-2~9b0d", "rotate certificate")
    assert isinstance(caught.value, AdaError) and caught.value.code == c["response"]["body"]["error"]["code"]
    assert caught.value.status == c["response"]["status"] and len(fake.calls) == 1 and clock == []


def test_a_reading_function_that_wrote_is_a_read_only_error():
    c = case("a reading function that wrote, on a follower")
    validate(c["response"]["body"], CONTRACT["result"])
    client, _ = ada(answered(c["response"]))
    with pytest.raises(ReadOnlyError) as caught:
        client.model("incidents").query({"a": 1})
    err = caught.value
    assert err.code == "E_READ_ONLY" and "writes" in err.message
    assert err.detail == {"run_id": "rrotor-1~c3", "function": "query"}


def test_a_record_past_the_cap_is_done_and_says_limit_exceeded():
    c = case("a record past the precedent cap")
    validate(c["response"]["body"], CONTRACT["result"])
    validate(c["response"]["body"]["data"], CONTRACT["limit_exceeded"])
    client, _ = ada(answered(c["response"]), answered(case("a call that is done")["response"]))
    r = client.model("incidents").record({"a": 1})
    assert r.done and r.limit_exceeded and r.data["cap"] == 50000
    assert not client.model("incidents").decide({"a": 1}).limit_exceeded


def test_retry_after_as_a_date_and_a_transport_that_answers_no_headers(clock):
    assert glyphh.client._retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == 0.0
    assert glyphh.client._retry_after("1.5") == 1.5 and glyphh.client._retry_after("soon") is None
    client, _ = ada((200, {"models": []}))
    assert client.models() == [] and client.cluster_seq == 0
