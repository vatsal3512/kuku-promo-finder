import re
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

from .models import Candidate

HOOK_TYPES = ["betrayal", "reveal", "injustice", "ultimatum", "rescue", "humiliation", "defiance", "romance", "confrontation"]
SPOILER_RANK = {"none": 0, "minor": 1, "major": 2}
SCORE_FIELDS = ["hook", "cliffhanger", "standalone", "escalation", "premise"]
WORD_SCORES = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "zero": 0}


def score(value):
    if isinstance(value, str):
        text = value.strip().lower()
        if text in WORD_SCORES:
            return WORD_SCORES[text]
        found = re.search(r"\d+(?:\.\d+)?", text)
        if not found:
            return value
        value = float(found.group())
        out_of = re.search(r"/\s*(\d+)", text)
        if out_of and float(out_of.group(1)) not in (0, 5):
            value = value * 5 / float(out_of.group(1))
    if isinstance(value, (int, float)):
        return max(0.0, min(5.0, float(value)))
    return value


def text_list(value):
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[;,]", value) if part.strip()]
    return value or []


Score = Annotated[float, BeforeValidator(score)]
TextList = Annotated[list[str], BeforeValidator(text_list)]


class ClipVerdict(BaseModel):
    clip: str
    notes: str = ""
    who: str = ""
    stakes: str = ""
    open_question: str = ""
    unexplained_refs: TextList = []
    hook: Score = Field(ge=0, le=5)
    cliffhanger: Score = Field(ge=0, le=5)
    standalone: Score = Field(ge=0, le=5)
    escalation: Score = Field(default=3, ge=0, le=5)
    premise: Score = Field(default=3, ge=0, le=5)
    spoiler_level: str = "none"
    policy_flags: TextList = []
    hook_type: str = "confrontation"
    why_it_works: str = ""
    judge_spread: float = 0.0
    standalone_min: float | None = None


class Verdicts(BaseModel):
    clips: list[ClipVerdict]


def judge_value(v: ClipVerdict, cfg: dict | None = None) -> float:
    llm_cfg = (cfg or {}).get("llm", {})
    core = (0.25 * v.hook + 0.25 * v.cliffhanger + 0.2 * v.standalone + 0.15 * v.escalation + 0.15 * v.premise) / 5
    core -= min(0.15, 0.04 * len(v.unexplained_refs))
    if v.spoiler_level.lower().startswith("major"):
        core -= llm_cfg.get("spoiler_major_penalty", 0.08)
    return round(core, 4)


def merge_verdicts(found: list[ClipVerdict]) -> ClipVerdict:
    if len(found) == 1:
        return found[0]
    first = found[0]
    data = first.model_dump()
    for name in SCORE_FIELDS:
        data[name] = round(sum(getattr(v, name) for v in found) / len(found), 2)
    sets = [{r.strip().lower() for r in v.unexplained_refs} for v in found]
    common = set.intersection(*sets)
    data["unexplained_refs"] = [r for r in first.unexplained_refs if r.strip().lower() in common]
    data["spoiler_level"] = max((v.spoiler_level.strip().lower() for v in found), key=lambda x: SPOILER_RANK.get(x, 0))
    flags = []
    for v in found:
        flags += [f for f in v.policy_flags if f not in flags]
    data["policy_flags"] = flags
    data["standalone_min"] = min(v.standalone for v in found)
    data["judge_spread"] = round(max(abs(getattr(a, n) - getattr(b, n)) for a in found for b in found for n in SCORE_FIELDS), 2)
    return ClipVerdict.model_validate(data)


def is_major_spoiler(c: Candidate) -> bool:
    return str(c.judge.get("spoiler_level", "")).lower().startswith("major")
