from collections import defaultdict

from pydantic import BaseModel, Field

from .providers import LLMError
from .models import Show

SYSTEM = (
    "You are a script coordinator for a vertical microdrama studio. You build the character list for a show "
    "from its episode summaries and speaker labels. Speaker labels in these scripts drift: the same person can "
    "appear under a role label (for example THE BEARDED STRANGER) before their name is known, and one role label "
    "can point at different people in different episodes. Use only evidence in the material. Reply in JSON."
)


class AliasRule(BaseModel):
    label: str
    first_episode: int
    last_episode: int
    name: str


class Character(BaseModel):
    name: str
    role: str = ""


class Bible(BaseModel):
    premise: str = Field(description="One sentence a stranger would understand")
    protagonist: str = ""
    characters: list[Character] = []
    aliases: list[AliasRule] = []


def label_table(show: Show, samples: int = 2) -> str:
    seen: dict[str, dict] = defaultdict(lambda: {"eps": set(), "lines": [], "hints": set()})
    for episode in show.episodes:
        for beat in episode.lines:
            row = seen[beat.label]
            row["eps"].add(episode.ep)
            row["hints"].update(d for d in beat.delivery if d[:1].isupper() and len(d.split()) == 1 and d.lower() not in ("cold",))
            if len(row["lines"]) < samples:
                row["lines"].append(f"ep{episode.ep}: {beat.text[:90]}")
    out = []
    for label, row in sorted(seen.items(), key=lambda kv: min(kv[1]["eps"])):
        eps = sorted(row["eps"])
        span = f"{eps[0]}-{eps[-1]}" if len(eps) > 1 else str(eps[0])
        out.append(f"{label} | episodes {span} ({len(eps)}) | e.g. " + " / ".join(row["lines"]))
    return "\n".join(out)


def build_bible(show: Show, llm, log=print) -> dict:
    summaries = "\n".join(f"Ep{e.ep}: {e.logline} | Continuity: {e.continuity}" for e in show.episodes)
    user = (
        f"SHOW: {show.name}\n\nEPISODE SUMMARIES:\n{summaries}\n\nSPEAKER LABELS (label | episodes | sample lines):\n"
        f"{label_table(show)}\n\n"
        "Return JSON with keys: premise (one sentence, no spoilers past episode 5), protagonist (name), "
        "characters (list of {name, role}), aliases (list of {label, first_episode, last_episode, name}). "
        "Add an alias rule for every speaker label that is a role, title or description of a named character, "
        "with the episode range where that mapping holds. Use the exact label text from the table. "
        "Skip labels you cannot map with confidence."
    )
    try:
        result = llm.json(SYSTEM, user, Bible)
    except LLMError as exc:
        log(f"Series bible failed, continuing with rule-based names: {exc}")
        return {}
    labels = {b.label for e in show.episodes for b in e.lines}
    aliases = [
        {"label": a.label.upper(), "episodes": [a.first_episode, a.last_episode], "name": a.name}
        for a in result.aliases
        if a.label.upper() in labels and a.name.strip()
    ]
    log(f"Series bible: {len(result.characters)} characters, {len(aliases)} alias rules")
    return {
        "premise": result.premise,
        "protagonist": result.protagonist,
        "characters": [c.model_dump() for c in result.characters],
        "aliases": aliases,
    }
