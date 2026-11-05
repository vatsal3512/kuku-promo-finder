import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import BaseModel
from rapidfuzz import fuzz

from .export import clock
from .llm import LLM
from .providers import LLMError
from .names import apply_names
from .parse import load_show, parse_time

SYSTEM = (
    "You are a promo editor for vertical microdramas. Find the best 20-60 second promo clips in the script. "
    "A promo opens on a hook in its first 3 seconds and ends on a cliffhanger. Give exact start and end "
    "timestamps in mm:ss.cc taken from the script. Reply in JSON."
)


class RawPromo(BaseModel):
    start: str
    end: str
    hook: str
    cliffhanger: str
    why: str = ""


class RawPromos(BaseModel):
    promos: list[RawPromo]


def render_plain(episode) -> str:
    rows = []
    for beat in episode.content:
        if beat.kind == "DIALOGUE":
            rows.append(f'{clock(beat.start)}-{clock(beat.end)} {beat.speaker}: "{beat.text}"')
        else:
            rows.append(f"{clock(beat.start)}-{clock(beat.end)} {beat.kind}: {beat.text}")
    return "\n".join(rows)


def check(promo: RawPromo, episode, gates: dict) -> list[str]:
    issues = []
    start, end = parse_time(promo.start), parse_time(promo.end)
    if start is None or end is None or end <= start:
        return ["unparseable or reversed timestamps"]
    duration = end - start
    if not gates["min_duration"] <= duration <= gates["max_duration"]:
        issues.append(f"duration {duration:.1f}s outside 20-60")
    if end > episode.duration + 0.01:
        issues.append("ends after the episode")
    for cut in (start, end):
        if any(b.start + 0.05 < cut < b.end - 0.05 for b in episode.lines):
            issues.append(f"cut at {clock(cut)} splits a line")
    opening = [b for b in episode.content if start - 0.05 <= b.start <= start + gates["max_hook_offset"]]
    if not any(fuzz.partial_ratio(promo.hook.lower(), b.text.lower()) >= 80 for b in opening):
        issues.append("named hook is not in the first 3 seconds")
    closing = [b for b in episode.content if end - 6 <= b.end <= end + 1.5]
    if not any(fuzz.partial_ratio(promo.cliffhanger.lower(), b.text.lower()) >= 80 for b in closing):
        issues.append("named cliffhanger is not at the cut")
    if not any(fuzz.partial_ratio(promo.hook.lower(), b.text.lower()) >= 80 for b in episode.content):
        issues.append("hook text not found anywhere in the episode")
    return issues


def run_baseline(input_path: str, model: str, episodes: list[int] | None, out_path: str, cfg: dict) -> dict:
    show = load_show(input_path)
    apply_names(show)
    llm = LLM(model, cfg["llm"])
    targets = [e for e in show.episodes if not episodes or e.ep in episodes]

    def ask(episode):
        user = f"EPISODE {episode.ep} SCRIPT:\n{render_plain(episode)}\n\nReturn JSON {{\"promos\": [{{\"start\": \"mm:ss.cc\", \"end\": \"mm:ss.cc\", \"hook\": quoted hook line, \"cliffhanger\": quoted final line, \"why\": short}}]}} with the 2 best promos."
        try:
            return episode, llm.json(SYSTEM, user, RawPromos), None
        except LLMError as exc:
            return episode, None, exc

    with ThreadPoolExecutor(max_workers=cfg["llm"].get("concurrency", 4)) as pool:
        results = list(pool.map(ask, targets))
    rows = []
    for episode, result, error in results:
        if error:
            rows.append({"episode": episode.ep, "error": str(error)[:200]})
            continue
        for promo in result.promos:
            issues = check(promo, episode, cfg["gates"])
            rows.append({"episode": episode.ep, **promo.model_dump(), "issues": issues, "valid": not issues})
    valid = [r for r in rows if r.get("valid")]
    scored = [r for r in rows if "valid" in r]
    counts: dict[str, int] = {}
    for r in scored:
        for issue in r["issues"]:
            key = "duration outside 20-60" if issue.startswith("duration") else "cut splits a line" if issue.startswith("cut at") else issue
            counts[key] = counts.get(key, 0) + 1
    summary = {
        "model": model,
        "episodes": len(targets),
        "promos": len(scored),
        "fully_valid": len(valid),
        "valid_ratio": round(len(valid) / len(scored), 3) if scored else 0.0,
        "issue_counts": counts,
        "usage": llm.usage(),
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary
