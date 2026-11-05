import copy
import json
import random
import re
import string
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import BaseModel, Field

from .features import beats_in, clip_time
from .llm import LLMError
from .models import Candidate, Show
from .rank import craft_check, overlap, select

HOOK_TYPES = ["betrayal", "reveal", "injustice", "ultimatum", "rescue", "humiliation", "defiance", "romance", "confrontation"]

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

PAIR_SYSTEM = (
    "You pick which of two promo clips for a vertical microdrama to run first as a paid ad aimed at people who "
    "have never seen the show. Prefer the clip that stops the scroll fastest, makes sense to a stranger, and ends "
    "on a cliffhanger that makes people install to see what happens. Reply in JSON."
)


class ClipVerdict(BaseModel):
    clip: str
    notes: str = ""
    who: str = ""
    stakes: str = ""
    open_question: str = ""
    unexplained_refs: list[str] = []
    hook: float = Field(ge=0, le=5)
    cliffhanger: float = Field(ge=0, le=5)
    standalone: float = Field(ge=0, le=5)
    escalation: float = Field(ge=0, le=5)
    premise: float = Field(ge=0, le=5)
    spoiler_level: str = "none"
    policy_flags: list[str] = []
    hook_type: str = "confrontation"
    why_it_works: str = ""
    judge_spread: float = 0.0
    standalone_min: float | None = None


class Verdicts(BaseModel):
    clips: list[ClipVerdict]


class PairChoice(BaseModel):
    reason: str = ""
    winner: str


def render_clip(candidate: Candidate, show: Show) -> str:
    rows = []
    current = 0
    for seg_index, beat in beats_in(candidate, show):
        if seg_index != current:
            rows.append("--- CUT ---")
            current = seg_index
        t = clip_time(candidate, seg_index, beat.start)
        stamp = f"[{int(t // 60)}:{int(t % 60):02d}]"
        if beat.kind == "DIALOGUE":
            tone = f" ({', '.join(beat.delivery[:2])})" if beat.delivery else ""
            rows.append(f'{stamp} {beat.speaker}{tone}: "{beat.text}"')
        elif beat.kind == "ACTION":
            rows.append(f"{stamp} VISUAL: {beat.text}")
        elif beat.kind == "SFX":
            rows.append(f"{stamp} SOUND: {beat.text}")
    return "\n".join(rows)


def judge_value(v: ClipVerdict, cfg: dict | None = None) -> float:
    llm_cfg = (cfg or {}).get("llm", {})
    core = (0.25 * v.hook + 0.25 * v.cliffhanger + 0.2 * v.standalone + 0.15 * v.escalation + 0.15 * v.premise) / 5
    core -= min(0.15, 0.04 * len(v.unexplained_refs))
    if v.spoiler_level.lower().startswith("major"):
        core -= llm_cfg.get("spoiler_major_penalty", 0.08)
    return round(core, 4)


def is_major_spoiler(c: Candidate) -> bool:
    return str(c.judge.get("spoiler_level", "")).lower().startswith("major")


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


COMPACT_TAIL = (
    "\n\nBe brief. Return JSON: {\"clips\": [{\"clip\": letter, \"notes\": at most 15 words, "
    "\"unexplained_refs\": [names or objects the clip never sets up], "
    "\"hook\": 0-5, \"cliffhanger\": 0-5, \"standalone\": 0-5, \"escalation\": 0-5, \"premise\": 0-5, "
    "\"spoiler_level\": none|minor|major, \"policy_flags\": [..], \"hook_type\": one of "
    + "|".join(HOOK_TYPES) + ", \"why_it_works\": at most 12 words}]} with one entry per clip."
)


def ask_verdicts(batch: list[Candidate], show: Show, judge_llm, compact: bool = False):
    letters = list(string.ascii_uppercase[: len(batch)])
    blocks = [f"CLIP {letter} ({c.duration:.0f}s)\n{render_clip(c, show)}" for letter, c in zip(letters, batch)]
    if compact:
        try:
            return batch, letters, judge_llm.json(JUDGE_SYSTEM, "\n\n".join(blocks) + COMPACT_TAIL, Verdicts), None
        except LLMError as exc:
            return batch, letters, None, exc
    user = "\n\n".join(blocks) + (
        "\n\nReturn JSON: {\"clips\": [{\"clip\": letter, \"notes\": str, \"who\": str, \"stakes\": str, "
        "\"open_question\": str, \"unexplained_refs\": [names or objects the clip never sets up], "
        "\"hook\": 0-5, \"cliffhanger\": 0-5, \"standalone\": 0-5, \"escalation\": 0-5, \"premise\": 0-5, "
        "\"spoiler_level\": none|minor|major, \"policy_flags\": [..], \"hook_type\": one of "
        + "|".join(HOOK_TYPES) + ", \"why_it_works\": str}]} with one entry per clip."
    )
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


SPOILER_RANK = {"none": 0, "minor": 1, "major": 2}
SCORE_FIELDS = ["hook", "cliffhanger", "standalone", "escalation", "premise"]


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


def judge_repeated(show: Show, items: list[Candidate], judge_llm, cfg: dict, seed: int, log=print) -> dict:
    repeats = max(1, cfg["llm"].get("judge_repeats", 2))
    runs = [judge_batches(show, items, judge_llm, cfg, seed=seed + i, log=log) for i in range(repeats)]
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


def clip_key(c: Candidate) -> str:
    return "|".join(f"{s.ep}:{s.start:.2f}-{s.end:.2f}" for s in c.segments)


class VerdictStore:
    def __init__(self, cache_dir: str, spec: str):
        name = re.sub(r"[^a-z0-9]+", "-", spec.lower()).strip("-")
        self.path = Path(cache_dir).parent / "verdicts" / f"{name}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.data: dict[str, dict] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.data[row["key"]] = row["verdict"]

    def get(self, c: Candidate) -> ClipVerdict | None:
        found = self.data.get(clip_key(c))
        return ClipVerdict.model_validate({"clip": "A", **found}) if found else None

    def put(self, c: Candidate, v: ClipVerdict):
        key = clip_key(c)
        row = v.model_dump(exclude={"clip"})
        with self.lock:
            self.data[key] = row
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"key": key, "verdict": row}, ensure_ascii=False) + "\n")


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
    log(f"Jury judged {judged_total} clips over {rounds} rounds, vetoed {vetoed} as not standalone")
    return {"used": True, "model": spec, "shortlist": size, "judged": judged_total, "vetoed": vetoed, "rounds": rounds, "usage": jury.usage()}


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
