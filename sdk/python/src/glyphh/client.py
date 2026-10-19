"""The client: your runtime's address and a runtime key; every call is one request to the runtime's API."""

from __future__ import annotations

import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Type, Union

DEFAULT_TIMEOUT = 90.0
#: How long, in seconds, a call keeps retrying (E_NO_HEAD; a read that could not reach the runtime) before it raises.
RETRY_DEADLINE = 30.0
WAITING = ("needs_input", "needs_approval")
FINAL = ("done", "failed", "expired", "cancelled")
#: An Ada model's functions that only read: safe to send again when the runtime could not be reached.
READS = ("query", "facts", "probabilities")
CLUSTER_SEQ, MIN_SEQ = "rrotor-cluster-seq", "rrotor-min-seq"

#: Sends one request: (method, url, headers, body) -> (status, body bytes) or (status, body bytes, headers).
#: Give your own to use another HTTP library; answer the headers for Retry-After and read-your-writes in a cluster.
Transport = Callable[
    [str, str, Mapping[str, str], Optional[bytes]],
    Union[Tuple[int, bytes], Tuple[int, bytes, Mapping[str, str]]],
]

_sleep, _now = time.sleep, time.monotonic  # the tests' seams


class AdaError(Exception):
    """The runtime refused, or could not be reached. `code` is the runtime's (E_AUTH, E_LIMIT, E_MODEL_MISSING,
    E_RUN_MISSING, E_BAD_REQUEST, ...), or E_UNREACHABLE; `status` is the HTTP status, 0 when there was none."""

    def __init__(
        self,
        code: str,
        message: str,
        status: int = 0,
        detail: Optional[Dict[str, Any]] = None,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
        self.detail = detail or {}
        self.retry_after = retry_after  # seconds, when the runtime said when to ask again

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.code!r}, {self.message!r}, status={self.status})"


class NoHeadError(AdaError):
    """E_NO_HEAD (503): the cluster has no head, so it takes no writes; reads go on. Raised once retries are spent."""


class NotCommittedError(AdaError):
    """E_NOT_COMMITTED (503): most voters do not hold the write yet. It is kept, and committed when they come back:
    do not send it again."""


class RunLostError(AdaError):
    """E_RUN_LOST (410): the node that held the run is no longer in the cluster; the run is gone."""


class ReadOnlyError(AdaError):
    """E_READ_ONLY: a function marked `"writes": false` wrote, on a cluster's follower; the store is untouched. Mark it
    `"writes": true` in the model's glyphh.json. `detail` has the run's `run_id` and `function`."""


TYPED: Dict[str, Type[AdaError]] = {
    "E_NO_HEAD": NoHeadError,
    "E_NOT_COMMITTED": NotCommittedError,
    "E_RUN_LOST": RunLostError,
    "E_READ_ONLY": ReadOnlyError,
}


def _error(
    code: str, message: str, status: int, detail: Dict[str, Any], retry_after: Optional[float]
) -> AdaError:
    return TYPED.get(code, AdaError)(code, message, status, detail, retry_after)


@dataclass(frozen=True)
class Result:
    """What a run answered: its status, and its data (the function's answer when done; why, when failed)."""

    run_id: str
    model: str
    version: int
    function: str
    status: str
    data: Any
    step: Optional[str]
    prompt: Optional[str]
    seconds: float

    @property
    def done(self) -> bool:
        return self.status == "done"

    @property
    def waiting(self) -> bool:
        """The run asks: `needs_input` or `needs_approval`; `prompt` says what. Answer with `resume`."""
        return self.status in WAITING

    @property
    def ended(self) -> bool:
        return self.status in FINAL

    @property
    def limit_exceeded(self) -> bool:
        """The run is done but indexed nothing: the store is at the licence's precedent cap. `data` has `message`,
        `precedents` and `cap`."""
        return self.done and isinstance(self.data, dict) and self.data.get("status") == "limit_exceeded"

    @classmethod
    def of(cls, body: Mapping[str, Any]) -> "Result":
        return cls(
            run_id=str(body["run_id"]),
            model=str(body["model"]),
            version=int(body["version"]),
            function=str(body["function"]),
            status=str(body["status"]),
            data=body.get("data"),
            step=body.get("step"),
            prompt=body.get("prompt"),
            seconds=float(body.get("seconds", 0)),
        )


def _urllib(
    method: str, url: str, headers: Mapping[str, str], body: Optional[bytes]
) -> Tuple[int, bytes, Dict[str, str]]:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:  # noqa: S310  # the caller's runtime
            return response.status, response.read(), dict(response.headers.items())
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers.items())


def _retry_after(value: Optional[str]) -> Optional[float]:
    """Retry-After as seconds: a number of them, or an HTTP date."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
    except (TypeError, ValueError):
        return None


def _retryable(err: AdaError, read: bool) -> bool:
    """E_NO_HEAD, any call: the cluster spec has the SDKs retry it (a follower with no head refuses a write before
    forwarding it). A read, also when the runtime could not be reached or a proxy in front of it answered 502, 503 or
    504. A write that may have been applied (E_UNREACHABLE, E_NOT_COMMITTED) is never sent again."""
    if err.code == "E_NO_HEAD":
        return True
    return read and (err.code == "E_UNREACHABLE" or (err.code == "E_RUNTIME" and err.status in (502, 503, 504)))


def _result(body: Mapping[str, Any]) -> Result:
    r = Result.of(body)
    if r.status == "failed" and isinstance(r.data, dict) and r.data.get("code") == "E_READ_ONLY":
        reason = str(r.data.get("reason") or f"{r.function} wrote, and it is marked read-only")
        raise ReadOnlyError("E_READ_ONLY", reason, 200, {"run_id": r.run_id, "function": r.function})
    return r


class Ada:
    """Your runtime, for one key.

        incidents = Ada().model("incidents")          # GLYPHH_RUNTIME_URL and GLYPHH_RUNTIME_KEY from the environment
        r = incidents.decide({"error": {...}})
        if r.done: apply(r.data["fix"])
        elif r.waiting: incidents.resume(r.run_id, ask(r.prompt))

    In a cluster: E_NO_HEAD, and a read that could not reach the runtime, are retried with backoff (Retry-After
    honoured) for up to `retry_deadline` seconds (0: never); the highest `Rrotor-Cluster-Seq` answered is sent back
    as `Rrotor-Min-Seq`, so a read sees this client's writes on whichever node answers it (`read_your_writes=False`:
    not sent).
    """

    def __init__(
        self,
        url: Optional[str] = None,
        key: Optional[str] = None,
        *,
        transport: Optional[Transport] = None,
        retry_deadline: float = RETRY_DEADLINE,
        read_your_writes: bool = True,
    ) -> None:
        self.url = (url or os.environ.get("GLYPHH_RUNTIME_URL") or "").rstrip("/")
        self.key = key or os.environ.get("GLYPHH_RUNTIME_KEY") or ""
        if not self.url or not self.key:
            raise AdaError("E_CONFIG", "the runtime's address and a runtime key are needed: GLYPHH_RUNTIME_URL, GLYPHH_RUNTIME_KEY")
        self._send = transport or _urllib
        self.retry_deadline, self.read_your_writes = retry_deadline, read_your_writes
        self._seq, self._lock = 0, threading.Lock()

    @property
    def cluster_seq(self) -> int:
        """The highest `Rrotor-Cluster-Seq` the runtime has answered this client (0: none, or not a cluster)."""
        return self._seq

    def _call(
        self, method: str, path: str, body: Optional[Mapping[str, Any]] = None, *, read: Optional[bool] = None
    ) -> Any:
        """One request, sent again while it may be (`_retryable`) and the deadline allows. `read`: safe to send again
        when it could not reach the runtime; a GET by default."""
        read = method == "GET" if read is None else read
        raw = None if body is None else json.dumps(body).encode()
        deadline, attempt = _now() + self.retry_deadline, 0
        while True:
            try:
                return self._once(method, path, raw)
            except AdaError as err:
                if not _retryable(err, read):
                    raise
                wait = err.retry_after
                if wait is None:  # 0.25 s doubling to 2 s, jittered by up to half
                    wait = min(2.0, 0.25 * 2**attempt) * (0.5 + random.random() / 2)  # noqa: S311
                if _now() + wait > deadline:
                    raise
                _sleep(wait)
                attempt += 1

    def _once(self, method: str, path: str, raw: Optional[bytes]) -> Any:
        headers = {"authorization": f"Bearer {self.key}", "accept": "application/json"}
        if raw is not None:
            headers["content-type"] = "application/json"
        if self.read_your_writes and self._seq:
            headers[MIN_SEQ] = str(self._seq)
        try:
            answer = self._send(method, f"{self.url}{path}", headers, raw)
        except OSError as e:
            raise AdaError("E_UNREACHABLE", f"the runtime could not be reached: {e}") from e
        status, content = answer[0], answer[1]
        got = {str(k).lower(): str(v) for k, v in (answer[2] if len(answer) > 2 else {}).items()}
        self._saw(got.get(CLUSTER_SEQ))
        try:
            parsed = json.loads(content) if content else {}
        except ValueError:
            parsed = {}
        if status >= 400:
            err = parsed.get("error", {}) if isinstance(parsed, dict) else {}
            code = err.get("code") or {401: "E_AUTH", 402: "E_LIMIT", 404: "E_NOT_FOUND"}.get(status, "E_RUNTIME")
            detail = {k: v for k, v in err.items() if k not in ("code", "message")}
            message = err.get("message") or f"the runtime answered {status}"
            raise _error(code, message, status, detail, _retry_after(got.get("retry-after")))
        return parsed

    def _saw(self, seq: Optional[str]) -> None:
        try:
            n = int(seq or 0)
        except ValueError:
            return
        with self._lock:
            self._seq = max(self._seq, n)

    # the runtime

    def models(self) -> List[Dict[str, Any]]:
        """The models deployed: each one's versions, the active one and its functions."""
        return list(self._call("GET", "/v1/models")["models"])

    def deploy(self, repo: str, commit: str, token: Optional[str] = None) -> Dict[str, Any]:
        """A commit of a model's GitHub repo (owner/name) as its next version; a token for a private repo."""
        body: Dict[str, Any] = {"repo": repo, "commit": commit}
        if token is not None:
            body["token"] = token
        return dict(self._call("POST", "/v1/models/deploy", body))

    def model(self, name: str) -> "Model":
        return Model(self, name)

    def run(self, run_id: str) -> Dict[str, Any]:
        """A run as the runtime shows it: status, function, times, the last Result."""
        return dict(self._call("GET", f"/v1/runs/{run_id}"))

    def log(self, run_id: str) -> List[Any]:
        return list(self._call("GET", f"/v1/runs/{run_id}/log")["lines"])

    def resume(self, run_id: str, answer: Any) -> Result:
        """Answer a run that waits (`needs_input`, `needs_approval`): the next Result."""
        return _result(self._call("POST", f"/v1/runs/{run_id}/continue", {"answer": answer}))

    def cancel(self, run_id: str) -> Result:
        return _result(self._call("POST", f"/v1/runs/{run_id}/cancel", {}))


class Model:
    """One model on the runtime. `call` reaches any function; the named ones are an Ada model's own."""

    def __init__(self, ada: Ada, name: str) -> None:
        self.ada, self.name = ada, name

    def call(
        self,
        function: str = "start",
        inputs: Optional[Mapping[str, Any]] = None,
        *,
        version: Optional[int] = None,
        clearance: Optional[float] = None,
    ) -> Result:
        body: Dict[str, Any] = {"model": self.name, "function": function, "inputs": dict(inputs or {})}
        if version is not None:
            body["version"] = version
        if clearance is not None:
            body["clearance"] = clearance
        return _result(self.ada._call("POST", "/v1/runs", body, read=function in READS))

    def resume(self, run_id: str, answer: Any) -> Result:
        return self.ada.resume(run_id, answer)

    def record(self, data: Mapping[str, Any], outcome: Optional[str] = None) -> Result:
        inputs: Dict[str, Any] = {"data": dict(data)}
        if outcome is not None:
            inputs["outcome"] = outcome
        return self.call("record", inputs)

    def query(self, data: Mapping[str, Any], *, clearance: Optional[float] = None) -> Result:
        return self.call("query", {"data": dict(data)}, clearance=clearance)

    def facts(self, data: Mapping[str, Any], *, top: Optional[int] = None, clearance: Optional[float] = None) -> Result:
        inputs: Dict[str, Any] = {"data": dict(data)}
        if top is not None:
            inputs["top"] = top
        return self.call("facts", inputs, clearance=clearance)

    def probabilities(self, data: Mapping[str, Any], *, clearance: Optional[float] = None) -> Result:
        return self.call("probabilities", {"data": dict(data)}, clearance=clearance)

    def decide(self, data: Mapping[str, Any], *, clearance: Optional[float] = None) -> Result:
        return self.call("decide", {"data": dict(data)}, clearance=clearance)

    def learn(self, *, sample: Optional[int] = None, clearance: Optional[float] = None) -> Result:
        """The model weighs its roles from its own precedents and calibrates; `sample` is how many of the newest
        to calibrate on."""
        return self.call("learn", {} if sample is None else {"sample": sample}, clearance=clearance)
