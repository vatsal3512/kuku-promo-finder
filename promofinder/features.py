from statistics import mean

from .models import Beat, Candidate, Show
from .rules import CONTEXT_START_RE, HOOK_PHRASE, STAKES_RE, Prior, hook_type_of, policy_flags


def beats_in(candidate: Candidate, show: Show) -> list[tuple[int, Beat]]:
    picked = []
    for i, seg in enumerate(candidate.segments):
        episode = show.by_ep[seg.ep]
        for beat in episode.content:
            if seg.start - 0.05 <= beat.start < seg.end - 0.3:
                picked.append((i, beat))
    return picked


def clip_time(candidate: Candidate, seg_index: int, t: float) -> float:
    offset = sum(s.duration for s in candidate.segments[:seg_index])
    return offset + t - candidate.segments[seg_index].start


def longest_gap(candidate: Candidate, picked: list[tuple[int, Beat]]) -> float:
    spans = sorted((clip_time(candidate, i, b.start), clip_time(candidate, i, b.end)) for i, b in picked)
    cursor, gap = 0.0, 0.0
    for start, end in spans:
        gap = max(gap, start - cursor)
        cursor = max(cursor, end)
    return round(max(gap, candidate.duration - cursor), 2)


def snippet(beat: Beat, limit: int = 90) -> str:
    text = beat.text if len(beat.text) <= limit else beat.text[: limit - 3].rsplit(" ", 1)[0] + "..."
    if beat.kind == "DIALOGUE":
        return f'{beat.speaker}: "{text}"'
    return f"[{beat.kind.lower()}] {text}"


def featurize(candidate: Candidate, show: Show, priors: dict[str, Prior]) -> Candidate:
    picked = beats_in(candidate, show)
    hook = show.beats[candidate.hook_uid]
    cliff = show.beats[candidate.cliff_uid]
    first, last = candidate.segments[0], candidate.segments[-1]
    total = candidate.duration
    intensities = [priors[b.uid].intensity for _, b in picked] or [0.0]
    times = [clip_time(candidate, i, b.start) for i, b in picked] or [0.0]
    half = total / 2
    early = [x for x, t in zip(intensities, times) if t < half] or [0.0]
    late = [x for x, t in zip(intensities, times) if t >= half] or [0.0]
    opening = [priors[b.uid].hook for i, b in picked if i == 0 and b.start - first.start <= 3.0] or [0.0]
    text = " ".join(b.text for _, b in picked)
    lines = [b for _, b in picked if b.kind == "DIALOGUE"]
    first_line = lines[0] if lines else None
    spoken = [(clip_time(candidate, i, b.start), clip_time(candidate, i, b.end), b) for i, b in picked if b.kind == "DIALOGUE"]
    first_line_at = min((s for s, _, _ in spoken), default=total)
    opening_words = sum(b.words for s, _, b in spoken if s < 3.0)
    talk_tail = total - max((e for _, e, _ in spoken), default=0.0)
    context = 0.0
    if first_line and (CONTEXT_START_RE.search(first_line.text) or first_line.text[:1].islower()):
        context = 1.0
    n_eps = max(e.ep for e in show.episodes)
    first_ep = min(s.ep for s in candidate.segments)
    last_ep = max(s.ep for s in candidate.segments)
    position = (last_ep - 1) / max(1, n_eps - 1)
    candidate.features = {
        "hook_prior": priors[hook.uid].hook,
        "opening_peak": round(max(opening), 4),
        "hook_offset": round(hook.start - first.start, 2) if hook.ep == first.ep else 99.0,
        "cliff_prior": priors[cliff.uid].cliff,
        "tail_after_cliff": round(last.end - cliff.end, 2),
        "intensity": round(mean(intensities), 4),
        "peak": round(max(intensities), 4),
        "escalation": round(mean(late) - mean(early), 4),
        "stakes": round(min(1.0, len(STAKES_RE.findall(text)) / 8), 4),
        "dead_air": longest_gap(candidate, picked),
        "lines": len(lines),
        "first_line_at": round(first_line_at, 2),
        "opening_words": opening_words,
        "hook_kind": hook.kind,
        "talk_tail": round(max(0.0, talk_tail), 2),
        "sound_off_hook": hook.kind in ("ACTION", "SFX") or hook.words <= 8,
        "context_risk": context,
        "first_episode": first_ep,
        "last_episode": last_ep,
        "series_position": round(position, 3),
        "speakers": sorted({b.speaker for b in lines}),
        "hook_text": snippet(hook),
        "cliff_text": snippet(cliff),
        "scenes": sorted({f"{b.ep}-{b.scene}" for _, b in picked}),
    }
    candidate.hook_type = hook_type_of(text)
    candidate.policy = policy_flags(text)
    candidate.arc = "premise" if position < 0.2 else "mid" if position < 0.65 else "late"
    candidate.why = (
        f"Opens on {HOOK_PHRASE[candidate.hook_type]} ({snippet(hook, 60)}) and cuts on "
        f"{snippet(cliff, 60)} before it resolves."
    )
    return candidate


def gates_pass(candidate: Candidate, cfg: dict) -> bool:
    g = cfg["gates"]
    f = candidate.features
    return (
        g["min_duration"] <= candidate.duration <= g["max_duration"]
        and f["hook_offset"] <= g["max_hook_offset"]
        and len(candidate.segments) <= g["max_segments"]
        and f["tail_after_cliff"] <= g["max_tail"] + 0.5
    )
