from pydantic import BaseModel

from .models import Candidate, Show
from .providers import LLMError
from .render import render_clip
from .verdicts import is_major_spoiler

PAIR_SYSTEM = (
    "You pick which of two promo clips for a vertical microdrama to run first as a paid ad aimed at people who "
    "have never seen the show. Prefer the clip that stops the scroll fastest, makes sense to a stranger, and ends "
    "on a cliffhanger that makes people install to see what happens. Reply in JSON."
)


class PairChoice(BaseModel):
    reason: str = ""
    winner: str


def pairwise_order(show: Show, chosen: list[Candidate], llm, cfg: dict, log=print) -> list[Candidate]:
    k = min(cfg["llm"].get("pairwise_top", 12), len(chosen))
    if k < 2:
        return chosen
    judge_llm = llm
    if cfg["llm"].get("judge_model"):
        from .llm import LLM
        judge_llm = LLM(cfg["llm"]["judge_model"], cfg["llm"])
    head, tail = chosen[:k], chosen[k:]

    def prefers(a: Candidate, b: Candidate) -> int:
        votes = 0
        for first, second, sign in ((a, b, 1), (b, a, -1)):
            user = (
                f"CLIP A ({first.duration:.0f}s)\n{render_clip(first, show)}\n\nCLIP B ({second.duration:.0f}s)\n"
                f"{render_clip(second, show)}\n\nReturn JSON: {{\"reason\": short, \"winner\": \"A\" or \"B\"}}"
            )
            try:
                choice = judge_llm.json(PAIR_SYSTEM, user, PairChoice)
            except LLMError:
                return 0
            pick = choice.winner.strip().upper()[:1]
            if pick == "A":
                votes += sign
            elif pick == "B":
                votes -= sign
        return 1 if votes == 2 else -1 if votes == -2 else 0

    swaps = 0
    passes = cfg["llm"].get("pairwise_passes", 2)
    for _ in range(passes):
        for i in range(len(head) - 1, 0, -1):
            if prefers(head[i], head[i - 1]) == 1:
                head[i - 1], head[i] = head[i], head[i - 1]
                swaps += 1
    log(f"Pairwise reorder of top {k}: {swaps} swaps over {passes} passes")
    for c in head:
        c.judge["pairwise_checked"] = True
    ordered = head + tail
    return [c for c in ordered if not is_major_spoiler(c)] + [c for c in ordered if is_major_spoiler(c)]
