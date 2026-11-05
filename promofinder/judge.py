import copy
import hashlib
import random
import string
from concurrent.futures import ThreadPoolExecutor

from .models import Candidate, Show
from .providers import LLMError
from .rank import craft_check, overlap, select
from .render import RENDER_VERSION, render_clip
from .store import VerdictStore
from .verdicts import HOOK_TYPES, ClipVerdict, Verdicts, judge_value, merge_verdicts

JUDGE_SYSTEM = (
    "You are a cold viewer scrolling TikTok who has never heard of this show, and also a strict promo editor. "
    "Each clip below is a 20-60 second cut from a vertical microdrama, given as a timed transcript. "
    "VISUAL lines are what is on screen, SOUND lines are audio, '--- CUT ---' joins two moments. "
    "Judge each clip only from what is inside it. First write short notes, then score each criterion 0-5:\n"
    "hook: would the first 3 seconds stop your thumb?\n"
    "cliffhanger: does it cut on an unresolved moment that makes you need the next part?\n"
    "standalone: can a stranger follow who these people are and what is at stake from the clip alone?\n"
    "escalation: does tension rise through the clip instead of sagging?\n"
    "premise: does it sell a hook-y series premise (relationship plus conflict) that makes you want to start the show?\n"
    "Also give spoiler_level (none, minor, major: does it give away a late twist?), policy_flags from "
    "[sexual, gore, violence, weapon, minor_in_danger, coercion, self_harm] that a Meta or TikTok ad reviewer "
    "would flag, hook_type, and why_it_works in at most 20 words, written plainly for an editor. Reply in JSON."
)

COMPACT_TAIL = (
    "\n\nBe brief. Return JSON: {\"clips\": [{\"clip\": letter, \"notes\": at most 15 words, "
    "\"unexplained_refs\": [names or objects the clip never sets up], "
    "\"hook\": 0-5, \"cliffhanger\": 0-5, \"standalone\": 0-5, \"escalation\": 0-5, \"premise\": 0-5, "
    "\"spoiler_level\": none|minor|major, \"policy_flags\": [..], \"hook_type\": one of "
    + "|".join(HOOK_TYPES) + ", \"why_it_works\": at most 12 words}]} with one entry per clip."
)

FULL_TAIL = (
    "\n\nReturn JSON: {\"clips\": [{\"clip\": letter, \"notes\": str, \"who\": str, \"stakes\": str, "
    "\"open_question\": str, \"unexplained_refs\": [names or objects the clip never sets up], "
    "\"hook\": 0-5, \"cliffhanger\": 0-5, \"standalone\": 0-5, \"escalation\": 0-5, \"premise\": 0-5, "
    "\"spoiler_level\": none|minor|major, \"policy_flags\": [..], \"hook_type\": one of "
    + "|".join(HOOK_TYPES) + ", \"why_it_works\": str}]} with one entry per clip."
)

JUDGE_VERSION = hashlib.sha256((JUDGE_SYSTEM + RENDER_VERSION).encode("utf-8")).hexdigest()[:8]


def judge_pool(scored: list[Candidate], cfg: dict) -> list[Candidate]:
    pool_cfg = copy.deepcopy(cfg)
    pool_cfg["selection"]["top"] = cfg["llm"]["judge_pool"]
    pool_cfg["selection"]["max_per_episode"] = max(3, cfg["selection"]["max_per_episode"])
    pool_cfg["selection"]["max_overlap"] = 0.6
    pool_cfg["selection"]["pool"] = max(cfg["selection"]["pool"], 1200)
    pool_cfg["selection"]["one_per_scene"] = False
    return select(scored, pool_cfg)


def judge_model_for(llm, cfg: dict):
    if cfg["llm"].get("judge_model"):
        from .llm import LLM
        return LLM(cfg["llm"]["judge_model"], cfg["llm"])
    return llm


def ask_verdicts(batch: list[Candidate], show: Show, judge_llm, compact: bool = False):
    letters = list(string.ascii_uppercase[: len(batch)])
    blocks = [f"CLIP {letter} ({c.duration:.0f}s)\n{render_clip(c, show)}" for letter, c in zip(letters, batch)]
    user = "\n\n".join(blocks) + (COMPACT_TAIL if compact else FULL_TAIL)
    try:
        return batch, letters, judge_llm.json(JUDGE_SYSTEM, user, Verdicts), None
    except LLMError as exc:
        return batch, letters, None, exc


def judge_batches(show: Show, items: list[Candidate], judge_llm, cfg: dict, seed: int, log=print, compact: bool = False, size: int | None = None) -> dict:
    rng = random.Random(seed)
    order = items[:]
    rng.shuffle(order)
    size = size or cfg["llm"]["judge_batch"]
    batches = [order[i:i + size] for i in range(0, len(order), size)]
    with ThreadPoolExecutor(max_workers=cfg["llm"].get("concurrency", 4)) as workers:
        results = list(workers.map(lambda b: ask_verdicts(b, show, judge_llm, compact), batches))
    verdicts: dict[str, ClipVerdict] = {}
    for batch, letters, found, error in results:
        if error is not None:
            log(f"Judge batch failed, keeping rule scores ({error})")
            continue
        by_letter = {v.clip.strip().upper()[:1]: v for v in found.clips}
        for letter, c in zip(letters, batch):
            if letter in by_letter:
                verdicts[c.cid] = by_letter[letter]
    return verdicts


def pass_store(judge_llm, cfg: dict, n: int):
    spec = getattr(judge_llm, "spec", None)
    if not spec or not cfg["llm"].get("verdict_store", True):
        return None
    return VerdictStore(cfg["llm"].get("cache_dir", ".cache/llm"), f"judge-{spec}-{JUDGE_VERSION}-pass{n}")


def judge_repeated(show: Show, items: list[Candidate], judge_llm, cfg: dict, seed: int, log=print) -> dict:
    repeats = max(1, cfg["llm"].get("judge_repeats", 2))
    runs = []
    for i in range(repeats):
        store = pass_store(judge_llm, cfg, i)
        known = {}
        if store:
            for c in items:
                stored = store.get(c)
                if stored:
                    known[c.cid] = stored
        missing = [c for c in items if c.cid not in known]
        fresh = judge_batches(show, missing, judge_llm, cfg, seed=seed + i, log=log) if missing else {}
        if store:
            for c in missing:
                if c.cid in fresh:
                    store.put(c, fresh[c.cid])
        runs.append({**known, **fresh})
    merged = {}
    for c in items:
        found = [r[c.cid] for r in runs if c.cid in r]
        if found:
            merged[c.cid] = merge_verdicts(found)
    return merged


def apply_verdict(c: Candidate, v: ClipVerdict, cfg: dict, lo: float, hi: float):
    blend = cfg["llm"].get("blend", 0.65)
    norm = min(1.0, max(0.0, (c.score - lo) / (hi - lo))) if hi > lo else 0.5
    premise_zone = cfg["llm"].get("premise_zone", 0.1)
    overridden = False
    if v.spoiler_level.lower().startswith("major") and c.features.get("series_position", 1.0) <= premise_zone:
        v = v.model_copy(update={"spoiler_level": "minor"})
        overridden = True
    value = judge_value(v, cfg)
    funnel = cfg["llm"].get("funnel_bonus", 0.1) * (1.0 - c.features["series_position"])
    c.judge = v.model_dump(exclude={"clip"})
    c.judge["judge_score"] = value
    c.judge["rule_score"] = c.score
    if overridden:
        c.judge["spoiler_note"] = "judge said major, but the clip is in the opening premise episodes"
    if v.hook_type not in HOOK_TYPES:
        c.judge["hook_type"] = c.hook_type
    floor = v.standalone if v.standalone_min is None else v.standalone_min
    if floor < cfg["llm"].get("min_standalone", 3):
        c.judge["rejected"] = f"standalone {floor:g} < {cfg['llm'].get('min_standalone', 3)} in at least one judging pass"
    elif v.cliffhanger < cfg["llm"].get("min_cliffhanger", 3):
        c.judge["rejected"] = f"cliffhanger {v.cliffhanger:g} < {cfg['llm'].get('min_cliffhanger', 3)}: it does not end on an unresolved moment"
    craft = craft_check(c, cfg)
    if craft:
        c.judge["craft"] = craft
    c.score = round((1 - blend) * norm + blend * value + funnel - sum(craft.values()), 4)


def same_moment(a: Candidate, b: Candidate) -> bool:
    return {s.ep for s in a.segments} == {s.ep for s in b.segments} and overlap(a, b) >= 0.5


def refine(show: Show, scored: list[Candidate], judged: list[Candidate], judge_llm, cfg: dict, lo: float, hi: float, log=print) -> list[Candidate]:
    seeds_n = cfg["llm"].get("refine_seeds", 20)
    per_seed = cfg["llm"].get("refine_variants", 3)
    if not seeds_n or not per_seed:
        return []
    promising = [c for c in judged if c.judge.get("hook", 0) >= 4]
    seeds = sorted(promising, key=lambda c: c.score, reverse=True)[:seeds_n]
    taken = {c.cid for c in judged}
    rest = sorted((c for c in scored if c.cid not in taken), key=lambda c: c.score, reverse=True)
    variants: list[Candidate] = []
    for seed in seeds:
        near = [c for c in rest if same_moment(c, seed) and c.key != seed.key
                and (abs(c.segments[0].start - seed.segments[0].start) > 1 or abs(c.segments[-1].end - seed.segments[-1].end) > 1)]
        for c in near[:per_seed]:
            variants.append(c)
            taken.add(c.cid)
            c.judge["refined_from"] = seed.cid
        rest = [c for c in rest if c.cid not in taken]
    if not variants:
        return []
    log(f"Refining {len(seeds)} strong clips with {len(variants)} alternative cuts")
    verdicts = judge_repeated(show, variants, judge_llm, cfg, seed=11, log=log)
    out = []
    for c in variants:
        origin = c.judge.get("refined_from")
        if c.cid in verdicts:
            apply_verdict(c, verdicts[c.cid], cfg, lo, hi)
            c.judge["refined_from"] = origin
            out.append(c)
        else:
            c.judge = {}
    wins = 0
    by_id = {c.cid: c for c in judged}
    for c in out:
        seed = by_id.get(c.judge["refined_from"])
        if seed and not c.judge.get("rejected") and c.score > seed.score:
            wins += 1
    log(f"Refinement: {wins} alternative cuts beat their original")
    return out


def learned_wave(show: Show, scored: list[Candidate], judged: list[Candidate], judge_llm, cfg: dict, lo: float, hi: float, log=print) -> dict:
    size = cfg["llm"].get("learned_wave", 30)
    if not size:
        return {"clips": [], "info": {"trained": False}}
    from .learn import learn_from_judge
    others = [c for c in scored if not c.judge]
    info = learn_from_judge(judged, others, show, cfg["llm"].get("learn_lambda", 20.0))
    if not info.get("trained"):
        return {"clips": [], "info": info}
    log(f"Learned judge predictor from {info['labels']} labels: grouped CV Spearman {info['cv_spearman']} (rule score alone {info['rule_score_spearman']}), ranking the next wave by {info['ranker']} score")
    key = (lambda c: c.features["predicted_judge"]) if info["ranker"] == "learned" else (lambda c: c.score)
    ranked = sorted(others, key=key, reverse=True)
    taken = list(judged)
    per_episode: dict[int, int] = {}
    wave = []
    for c in ranked:
        if len(wave) >= size:
            break
        ep = c.segments[0].ep
        if per_episode.get(ep, 0) >= 2 or any(overlap(c, t) >= 0.5 for t in taken):
            continue
        wave.append(c)
        taken.append(c)
        per_episode[ep] = per_episode.get(ep, 0) + 1
    verdicts = judge_repeated(show, wave, judge_llm, cfg, seed=31, log=log)
    out = []
    for c in wave:
        if c.cid in verdicts:
            apply_verdict(c, verdicts[c.cid], cfg, lo, hi)
            c.judge["learned_pick"] = True
            out.append(c)
    values = [c.judge["judge_score"] for c in out]
    first = [c.judge["judge_score"] for c in judged if "judge_score" in c.judge]
    info["wave_judged"] = len(out)
    info["wave_mean_judge"] = round(sum(values) / len(values), 4) if values else None
    info["first_pool_mean_judge"] = round(sum(first) / len(first), 4) if first else None
    info["wave_rejected"] = sum(1 for c in out if c.judge.get("rejected"))
    log(f"Learned wave: {len(out)} new clips, mean judge {info['wave_mean_judge']} vs first pool {info['first_pool_mean_judge']}")
    return {"clips": out, "info": info}


def judge_show(show: Show, scored: list[Candidate], llm, cfg: dict, log=print):
    judge_llm = judge_model_for(llm, cfg)
    pool = judge_pool(scored, cfg)
    log(f"Judging {len(pool)} diverse candidates blind")
    base = [c.score for c in pool]
    lo, hi = min(base), max(base)
    verdicts = judge_repeated(show, pool, judge_llm, cfg, seed=7, log=log)
    for c in pool:
        if c.cid in verdicts:
            apply_verdict(c, verdicts[c.cid], cfg, lo, hi)
    judged = [c for c in pool if c.judge]
    learned = learned_wave(show, scored, judged, judge_llm, cfg, lo, hi, log)
    judged += learned["clips"]
    judged += refine(show, scored, judged, judge_llm, cfg, lo, hi, log)
    for c in scored:
        if not c.judge:
            c.score = round(c.score * 0.25, 4)
    rejected = [c for c in judged if c.judge.get("rejected")]
    log(f"Judged {len(judged)} clips in total, {len(rejected)} rejected as not standalone")
    return judged, learned["info"]
