import copy

from .judge import judge_batches
from .models import Candidate, Show
from .providers import LLMError
from .rank import select
from .store import VerdictStore
from .verdicts import SCORE_FIELDS, ClipVerdict, judge_value


def jury_check(show: Show, eligible: list[Candidate], cfg: dict, log=print) -> dict:
    spec = cfg["llm"].get("jury_model")
    size = cfg["llm"].get("jury_top", 25)
    if not spec or not size:
        return {"used": False}
    from .llm import LLM
    try:
        jury = LLM(spec, cfg["llm"])
    except LLMError as exc:
        log(f"Jury model unavailable, skipping ({exc})")
        return {"used": False, "error": str(exc)}
    store = VerdictStore(cfg["llm"].get("cache_dir", ".cache/llm"), spec)
    shortlist_cfg = copy.deepcopy(cfg)
    shortlist_cfg["selection"]["top"] = size
    floor = cfg["llm"].get("min_standalone", 3)
    vetoed, judged_total, rounds = 0, 0, 0
    verdicts: dict[str, ClipVerdict] = {}
    for rounds in range(1, 5):
        pool = [c for c in eligible if not c.judge.get("rejected")]
        shortlist = select(pool, shortlist_cfg)
        todo = [c for c in shortlist if "jury" not in c.judge]
        if not todo:
            break
        log(f"Second-model jury ({spec}), round {rounds}: {len(todo)} clips")
        reused = 0
        for c in todo:
            known = store.get(c)
            if known is not None:
                verdicts[c.cid] = known
                reused += 1
        if reused:
            log(f"Reused {reused} stored jury verdicts")
        for attempt in range(3):
            missing = [c for c in todo if c.cid not in verdicts]
            if not missing:
                break
            fresh = judge_batches(show, missing, jury, cfg, seed=41 + 10 * rounds + attempt, log=log, compact=cfg["llm"].get("jury_compact", True), size=cfg["llm"].get("jury_batch", 1))
            by_id = {c.cid: c for c in missing}
            for cid, v in fresh.items():
                store.put(by_id[cid], v)
            verdicts.update(fresh)
        for c in todo:
            v = verdicts.get(c.cid)
            if not v:
                c.judge["jury"] = {"model": spec, "missing": True}
                continue
            judged_total += 1
            first = {n: c.judge.get(n) for n in SCORE_FIELDS}
            c.judge["jury"] = {"model": spec, **{n: getattr(v, n) for n in SCORE_FIELDS}, "unexplained_refs": v.unexplained_refs, "spoiler_level": v.spoiler_level}
            for n in SCORE_FIELDS:
                if first[n] is not None:
                    c.judge[n] = round((first[n] + getattr(v, n)) / 2, 2)
            jury_value = judge_value(v, cfg)
            own = c.judge.get("judge_score", jury_value)
            c.judge["judge_score"] = round((own + jury_value) / 2, 4)
            c.score = round(c.score + cfg["llm"].get("blend", 0.65) * (c.judge["judge_score"] - own), 4)
            if v.standalone < floor:
                c.judge["rejected"] = f"second-model jury gave standalone {v.standalone:g} < {floor}"
                vetoed += 1
            elif c.judge.get("cliffhanger", 5) < cfg["llm"].get("min_cliffhanger", 3):
                c.judge["rejected"] = f"both judges together rate the cliffhanger {c.judge['cliffhanger']:g} < {cfg['llm'].get('min_cliffhanger', 3)}"
                vetoed += 1
    log(f"Jury judged {judged_total} clips over {rounds} rounds, vetoed {vetoed} as not standalone")
    return {"used": True, "model": spec, "shortlist": size, "judged": judged_total, "vetoed": vetoed, "rounds": rounds, "usage": jury.usage()}
