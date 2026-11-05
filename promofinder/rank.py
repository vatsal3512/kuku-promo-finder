from .models import Candidate


CRAFT = {
    "weak_open": 0.06,
    "thin_open_words": 4,
    "thin_open": 0.04,
    "silent_tail_from": 5.0,
    "silent_tail_per_second": 0.008,
    "long_from": 50.0,
    "long_per_second": 0.004,
}


def craft_check(candidate: Candidate, cfg: dict) -> dict:
    k = {**CRAFT, **cfg.get("craft", {})}
    f = candidate.features
    out = {}
    if f.get("first_line_at", 0.0) > 3.0:
        out["no line in first 3s"] = k["weak_open"]
    elif f.get("hook_kind", "DIALOGUE") == "DIALOGUE" and f.get("opening_words", 99) < k["thin_open_words"]:
        out["thin opening line"] = k["thin_open"]
    tail = f.get("talk_tail", 0.0) - k["silent_tail_from"]
    if tail > 0:
        out["silent tail after last line"] = round(k["silent_tail_per_second"] * tail, 4)
    extra = candidate.duration - k["long_from"]
    if extra > 0:
        out["long for a promo"] = round(k["long_per_second"] * extra, 4)
    return out


def base_score(candidate: Candidate, cfg: dict) -> float:
    w, p = cfg["weights"], cfg["penalties"]
    f = candidate.features
    hook = max(f["hook_prior"], f["opening_peak"])
    funnel = 1.0 - f["series_position"]
    parts = {
        "hook": w["hook"] * hook,
        "cliff": w["cliff"] * f["cliff_prior"],
        "intensity": w["intensity"] * f["intensity"],
        "stakes": w["stakes"] * f["stakes"],
        "escalation": w["escalation"] * max(0.0, f["escalation"]),
        "sound_off": w["sound_off"] * (1.0 if f["sound_off_hook"] else 0.0),
        "funnel": w["funnel"] * funnel,
        "dead_air": -p["dead_air_per_second"] * max(0.0, f["dead_air"] - 4.0),
        "context": -p["context"] * f["context_risk"],
        "format": -p.get(candidate.kind, 0.0),
    }
    if any(flag.endswith(":high") for flag in candidate.policy):
        parts["policy"] = -p["policy_high"]
    elif any(flag.endswith(":medium") for flag in candidate.policy):
        parts["policy"] = -p["policy_medium"]
    candidate.parts = {k: round(v, 4) for k, v in parts.items()}
    return round(sum(parts.values()), 4)


def overlap(a: Candidate, b: Candidate) -> float:
    best = 0.0
    for x in a.segments:
        for y in b.segments:
            if x.ep != y.ep:
                continue
            inter = max(0.0, min(x.end, y.end) - max(x.start, y.start))
            union = max(x.end, y.end) - min(x.start, y.start)
            if union > 0:
                best = max(best, inter / min(x.duration, y.duration) if inter else 0.0)
    return best


def similarity(a: Candidate, b: Candidate) -> float:
    sim = overlap(a, b)
    if a.hook_type == b.hook_type:
        sim += 0.15
    if a.features["first_episode"] == b.features["first_episode"]:
        sim += 0.1
    if a.hook_uid == b.hook_uid or a.cliff_uid == b.cliff_uid:
        sim += 0.5
    return min(sim, 1.0)


def shares_scene(a: Candidate, b: Candidate) -> bool:
    return bool(set(a.features.get("scenes", [])) & set(b.features.get("scenes", [])))


def select(candidates: list[Candidate], cfg: dict) -> list[Candidate]:
    s = cfg["selection"]
    pool = sorted(candidates, key=lambda c: c.score, reverse=True)[: s["pool"]]
    chosen: list[Candidate] = []
    per_episode: dict[int, int] = {}
    episodes = {seg.ep for c in candidates for seg in c.segments}
    cap = max(s["max_per_episode"], -(-s["top"] // max(1, len(episodes))))
    while pool and len(chosen) < s["top"]:
        best, best_value = None, float("-inf")
        for c in pool:
            if any(overlap(c, x) > s["max_overlap"] for x in chosen):
                continue
            if s.get("one_per_scene") and any(shares_scene(c, x) for x in chosen):
                continue
            eps = {seg.ep for seg in c.segments}
            if any(per_episode.get(ep, 0) >= cap for ep in eps):
                continue
            penalty = max((similarity(c, x) for x in chosen), default=0.0)
            value = s["mmr_lambda"] * c.score - (1 - s["mmr_lambda"]) * penalty
            if value > best_value:
                best, best_value = c, value
        if best is None:
            break
        chosen.append(best)
        pool.remove(best)
        for seg in best.segments:
            per_episode[seg.ep] = per_episode.get(seg.ep, 0) + 1
    return chosen


RISKY = ("medium", "high")


def risk_count(candidate: Candidate) -> int:
    from .export import merge_flags
    flags = merge_flags(candidate.policy, candidate.judge.get("policy_flags", []))
    return sum(1 for f in flags if f.rpartition(":")[2] in RISKY)


def pick_control(chosen: list[Candidate], cfg: dict) -> list[Candidate]:
    rule = cfg["selection"]
    limit = rule.get("control_max_position", 0.2)
    pool = [
        c for c in chosen
        if c.features.get("series_position", 1.0) <= limit
        and not str(c.judge.get("spoiler_level", "")).lower().startswith("major")
    ]
    if not pool:
        return chosen
    best = min(pool, key=lambda c: (risk_count(c), -c.judge.get("judge_score", 0.0), chosen.index(c)))
    best.judge["control_reason"] = f"earliest-funnel clip (series position <= {limit}) with the fewest medium/high ad-policy flags, then the best judge score"
    return [best] + [c for c in chosen if c is not best]
