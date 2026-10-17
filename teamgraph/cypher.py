"""The ONLY module allowed to send Cypher to FalkorDB (enforced by tests/test_invariants.py).

Every query is a constant registered at import time through `register()`. `run()` refuses any text that was not
registered, and every value travels as a query parameter, never by string formatting. So an unsafe, string-built
query cannot be written by accident: it would fail at runtime here, and the invariant test fails on any `.query(`
call outside this file."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Protocol


class Query(str):
    """Marker type: only register() creates these, so a plain (possibly string-built) str is refused by run()."""

    __slots__ = ()


Param = str | int | float | bool | None | Sequence["Param"] | Mapping[str, "Param"]
_REGISTERED: set[str] = set()
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class Graph(Protocol):
    name: str

    def query(self, q: str, params: Mapping[str, Any] | None = None) -> Any: ...


def register(queries: Mapping[str, str]) -> dict[str, Query]:
    """Register constant Cypher. Call only at module import with literal strings."""
    out: dict[str, Query] = {}
    for k, text in queries.items():
        if not _NAME.match(k):
            raise ValueError(f"bad query name {k!r}")
        _REGISTERED.add(text)
        out[k] = Query(text)
    return out


def _check(v: Param, depth: int = 0) -> None:
    if depth > 4:
        raise ValueError("parameter nesting too deep")
    if isinstance(v, float):
        if not math.isfinite(v):
            raise ValueError("non-finite parameter")
        return
    if v is None or isinstance(v, (str, int, bool)):
        return
    if isinstance(v, Mapping):
        for k, x in v.items():
            if not isinstance(k, str) or not _NAME.match(k):
                raise ValueError(f"bad map key {k!r}")
            _check(x, depth + 1)
        return
    if isinstance(v, Sequence):
        for x in v:
            _check(x, depth + 1)
        return
    raise TypeError(f"unsupported parameter type {type(v).__name__}")


def run(g: Graph, q: Query, params: Mapping[str, Param] | None = None) -> list[list[Any]]:
    """Run a registered query with parameters; returns the result rows."""
    if type(q) is not Query or q not in _REGISTERED:
        raise ValueError("refusing unregistered Cypher (build queries with cypher.register at import time)")
    p = dict(params or {})
    for k, v in p.items():
        if not _NAME.match(k):
            raise ValueError(f"bad parameter name {k!r}")
        _check(v)
    rows: list[list[Any]] = g.query(q, p).result_set
    return rows
