import re
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

from .export import clock
from .providers import LLMError
from .models import Episode, Show
from .rules import Prior


def line_id(value):
    if isinstance(value, str):
        found = re.search(r"\d+", value)
        return int(found.group()) if found else -1
    return value


def strength(value):
    if isinstance(value, str):
        found = re.search(r"\d+", value)
        value = int(found.group()) if found else 3
    if isinstance(value, (int, float)):
        return max(1, min(5, int(round(value))))
    return value


LineId = Annotated[int, BeforeValidator(line_id)]
Strength = Annotated[int, BeforeValidator(strength)]

SYSTEM = (
    "You are a performance-marketing editor who cuts 20-60 second promos for vertical microdramas "
    "(ReelShort, DramaBox style). You read one episode script, where every line has an id like [b12]. "
    "A HOOK is a moment that stops a scrolling viewer within 3 seconds: a slap, a reveal, a public humiliation, "
    "a shocking or cruel line, a threat, a rescue. A CLIFFHANGER is a moment to cut on: unresolved danger, an open "
    "question, a reveal with no answer yet. Lines marked VISUAL are on-screen action, SOUND is audio. "
    "Refer to moments only by their id number. Never write timestamps. Reply in JSON."
)


class HookTag(BaseModel):
    beat: LineId
    hook_type: str = ""
    strength: Strength = Field(default=3, ge=1, le=5)
    sound_off: bool = False


class CliffTag(BaseModel):
    beat: LineId
    strength: Strength = Field(default=3, ge=1, le=5)
    open_question: str = ""


class EpisodeTags(BaseModel):
    hooks: list[HookTag] = []
    cliffhangers: list[CliffTag] = []
    turning_points: list[LineId] = []


def render_episode(episode: Episode) -> str:
    rows = []
    for beat in episode.content:
        stamp = clock(beat.start)
        if beat.kind == "DIALOGUE":
            tone = f" ({', '.join(beat.delivery[:3])})" if beat.delivery else ""
            rows.append(f'[b{beat.idx}] {stamp} {beat.speaker}{tone}: "{beat.text}"')
        elif beat.kind == "ACTION":
            rows.append(f"[b{beat.idx}] {stamp} VISUAL: {beat.text}")
        elif beat.kind == "SFX":
            rows.append(f"[b{beat.idx}] {stamp} SOUND: {beat.text}")
        else:
            rows.append(f"[b{beat.idx}] {stamp} TEXT: {beat.text}")
    return "\n".join(rows)


def tag_episode(episode: Episode, llm, extra: dict | None = None) -> EpisodeTags:
    user = (
        f"EPISODE {episode.ep}\nSummary: {episode.logline}\n\nSCRIPT:\n{render_episode(episode)}\n\n"
        "Return JSON: {\"hooks\": [{\"beat\": id, \"hook_type\": one of betrayal|reveal|injustice|ultimatum|rescue|"
        "humiliation|defiance|romance|confrontation, \"strength\": 1-5, \"sound_off\": true if it works muted}], "
        "\"cliffhangers\": [{\"beat\": id, \"strength\": 1-5, \"open_question\": short}], "
        "\"turning_points\": [ids]}. Give the 3-6 best hooks and the 2-4 best cliffhangers, strongest first."
    )
    return llm.json(SYSTEM, user, EpisodeTags, **({"extra": extra} if extra else {}))


def tag_show(show: Show, priors: dict[str, Prior], llm, cfg: dict, log=print) -> dict:
    blend = cfg["llm"].get("blend", 0.65)
    report = {}

    def safe(episode):
        try:
            return episode, tag_episode(episode, llm, cfg["llm"].get("tag_extra")), None
        except LLMError as exc:
            return episode, None, exc

    with ThreadPoolExecutor(max_workers=cfg["llm"].get("concurrency", 4)) as pool:
        results = list(pool.map(safe, show.episodes))
    for episode, tags, error in results:
        by_idx = {b.idx: b for b in episode.content}
        if error is not None:
            log(f"Ep{episode.ep}: tagging failed, rules only ({error})")
            report[episode.ep] = {"error": str(error)[:200]}
            continue
        hook_llm = {by_idx[t.beat].uid: t.strength / 5 for t in tags.hooks if t.beat in by_idx}
        cliff_llm = {by_idx[t.beat].uid: t.strength / 5 for t in tags.cliffhangers if t.beat in by_idx}
        turning = {by_idx[i].uid for i in tags.turning_points if i in by_idx}
        for beat in episode.content:
            prior = priors[beat.uid]
            prior.hook = round((1 - blend) * prior.hook + blend * hook_llm.get(beat.uid, 0.0), 4)
            prior.cliff = round((1 - blend) * prior.cliff + blend * cliff_llm.get(beat.uid, 0.0), 4)
            if beat.uid in turning:
                prior.intensity = min(1.0, prior.intensity + 0.15)
        dropped = len(tags.hooks) + len(tags.cliffhangers) - len(hook_llm) - len(cliff_llm)
        report[episode.ep] = {"hooks": len(hook_llm), "cliffs": len(cliff_llm), "invalid_ids": dropped}
        log(f"Ep{episode.ep}: {len(hook_llm)} hooks, {len(cliff_llm)} cliffhangers tagged" + (f", {dropped} invalid ids dropped" if dropped else ""))
    return report
