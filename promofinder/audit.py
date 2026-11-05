import json
import statistics
from pathlib import Path

from .evaluate import load_run
from .judge import judge_batches
from .store import VerdictStore
from .verdicts import judge_value
from .llm import LLM
from .models import Candidate, Segment
from .names import apply_names
from .parse import load_show

FIELDS = ["hook", "cliffhanger", "standalone", "escalation", "premise"]


def as_candidate(tag: str, promo: dict) -> Candidate:
    segments = [Segment(s["episode"], s["start_seconds"], s["end_seconds"]) for s in promo["segments"]]
    return Candidate(cid=f"{tag}:{promo['rank']}", kind=promo["format"], segments=segments, hook_uid="", cliff_uid="")


def audit(run_dirs: list[str], input_path: str, model: str, cfg: dict, top: int = 15, out_path: str | None = None, log=print, compact: bool = True) -> dict:
    show = load_show(input_path)
    aliases = []
    bible = Path(run_dirs[0]) / "series_bible.json"
    if bible.exists():
        aliases = json.loads(bible.read_text(encoding="utf-8")).get("aliases", [])
    apply_names(show, list(cfg.get("names") or []) + aliases)
    items, owners = [], {}
    seen = {}
    for tag, run_dir in zip("ABCDEFGH", run_dirs):
        for promo in load_run(run_dir)["promos"][:top]:
            c = as_candidate(tag, promo)
            key = tuple((s.ep, round(s.start, 1), round(s.end, 1)) for s in c.segments)
            if key in seen:
                owners.setdefault(seen[key].cid, []).append(tag)
                continue
            seen[key] = c
            owners[c.cid] = [tag]
            items.append(c)
    llm = LLM(model, cfg["llm"])
    store = VerdictStore(cfg["llm"].get("cache_dir", ".cache/llm"), f"audit-{model}")
    verdicts = {}
    for c in items:
        known = store.get(c)
        if known is not None:
            verdicts[c.cid] = known
    log(f"Audit: {len(verdicts)} of {len(items)} clips already judged by {model}")
    for attempt in range(4):
        missing = [c for c in items if c.cid not in verdicts]
        if not missing:
            break
        fresh = judge_batches(show, missing, llm, cfg, seed=23 + attempt, log=log, compact=compact)
        by_id = {c.cid: c for c in missing}
        for cid, v in fresh.items():
            store.put(by_id[cid], v)
        verdicts.update(fresh)

    per_run: dict[str, list[dict]] = {tag: [] for tag in "ABCDEFGH"[: len(run_dirs)]}
    for c in items:
        v = verdicts.get(c.cid)
        if not v:
            continue
        row = {f: getattr(v, f) for f in FIELDS}
        row["unexplained_refs"] = len(v.unexplained_refs)
        row["value"] = judge_value(v, cfg)
        row["clip"] = c.cid
        row["passes_standalone"] = v.standalone >= cfg["llm"].get("min_standalone", 3)
        for tag in owners[c.cid]:
            per_run[tag].append(row)
    summary = {"usage": llm.usage(), "judge_model": model, "clips_judged": len(verdicts), "clips_total": len(items), "runs": {}}
    for tag, run_dir in zip(per_run, run_dirs):
        rows = per_run[tag]
        if not rows:
            continue
        stats = {f: round(statistics.mean(r[f] for r in rows), 2) for f in FIELDS + ["unexplained_refs", "value"]}
        stats["standalone_pass_rate"] = round(sum(r["passes_standalone"] for r in rows) / len(rows), 3)
        stats["n"] = len(rows)
        summary["runs"][Path(run_dir).name] = stats
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(json.dumps({**summary, "rows": per_run}, indent=2), encoding="utf-8")
    return summary
