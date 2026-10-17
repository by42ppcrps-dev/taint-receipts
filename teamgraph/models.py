"""Validated input models: every externally supplied value is checked here before it reaches a tool or query."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Id = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")]
OptId = Annotated[str, Field(max_length=64, pattern=r"^[A-Za-z0-9_.:-]*$")]
OptName = Annotated[str, Field(max_length=32)]
AgentName = Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")]
Short = Annotated[str, Field(max_length=200)]
Text = Annotated[str, Field(max_length=2000)]
Value = Annotated[str, Field(min_length=1, max_length=32)]
DemoAgent = Literal["Scout", "Quill", "Reel", "Lens"]


class DemoRequest(BaseModel):
    """Body of a POST to the local demo UI (teamgraph.web). Unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")
    claim: Id = "c-battery"
    value: Value = "3.5"
    reason: Short = "decimal dropped"
    artifact: Id = "short"
    agent: DemoAgent = "Reel"
    k: Annotated[int, Field(ge=1, le=10)] = 5
