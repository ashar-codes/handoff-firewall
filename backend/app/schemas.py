import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Rule(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    label: str = Field(min_length=1, max_length=180)
    fields: list[str] = Field(min_length=1, max_length=10)
    mandatory: bool = True
    condition: dict[str, str] | None = None
    expected: str | None = None
    review: bool = False
    owner_id: str | None = None
    depends_on: list[str] = Field(default_factory=list, max_length=10)
    precedence: Literal["none", "latest_document"] = "none"
    description: str = Field(default="", max_length=2000)


class TemplateIn(Strict):
    name: str = Field(min_length=1, max_length=180)
    source: str = Field(min_length=1, max_length=80)
    destination: str = Field(min_length=1, max_length=80)
    rules: list[Rule] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_graph(self):
        ids = {r.id for r in self.rules}
        if len(ids) != len(self.rules):
            raise ValueError("Requirement IDs must be unique")
        mapping = {r.id: r.depends_on for r in self.rules}
        visited = set()

        def visit(k, stack):
            if k in stack:
                raise ValueError("Dependency cycle")
            if k not in ids:
                raise ValueError("Unknown dependency")
            if k in visited:
                return
            for child in mapping[k]:
                visit(child, stack | {k})
            visited.add(k)

        for k in ids:
            visit(k, set())
        for r in self.rules:
            if any(not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", f) for f in r.fields):
                raise ValueError("Fields must be lowercase identifiers with underscores")
            if r.condition and (set(r.condition) != {"field", "equals"}):
                raise ValueError("Conditions require field and equals")
        return self


class CaseIn(Strict):
    title: str = Field(min_length=1, max_length=180)
    business_key: str = Field(min_length=1, max_length=120)
    template_id: str
    owner_id: str | None = None
    goal: str = Field(min_length=1, max_length=3000)
    context: dict[str, str] = Field(default_factory=dict)


class LoginIn(Strict):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class UserIn(Strict):
    email: str = Field(min_length=3, max_length=254)
    name: str = Field(min_length=1, max_length=120)
    role: Literal["Administrator", "Policy Manager", "Operator", "Reviewer", "Viewer"]
    password: str = Field(min_length=12, max_length=256)


class DecisionIn(Strict):
    fingerprint: str
    decision: Literal["APPROVED", "REJECTED"]
    comment: str = Field(min_length=1, max_length=2000)


class ReplyIn(Strict):
    values: dict[str, str] = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=1, max_length=2000)


class ReviewIn(Strict):
    accepted: bool
    comment: str = Field(min_length=1, max_length=2000)
    supersedes: list[str] = Field(default_factory=list, max_length=50)


class TransitionIn(Strict):
    state: Literal["ESCALATED", "VERIFYING"]
    reason: str = Field(min_length=1, max_length=2000)


class Candidate(Strict):
    requirement_id: str
    field: str
    value: str = Field(min_length=1, max_length=2000)
    quote: str = Field(min_length=1, max_length=3000)


class Extracted(Strict):
    candidates: list[Candidate] = Field(default_factory=list, max_length=50)
