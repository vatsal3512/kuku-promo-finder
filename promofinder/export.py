import csv
import json
from pathlib import Path

from .features import beats_in, clip_time
from .models import Candidate, Show
from .rules import POLICY


def clock(t: float) -> str:
    minutes, seconds = divmod(max(0.0, t), 60)
    return f"{int(minutes):02d}:{seconds:05.2f}"


def beat_view(show: Show, uid: str) -> dict:
    beat = show.beats[uid]
    return {
        "episode": beat.ep,
        "time": clock(beat.start),
        "kind": beat.kind,
        "speaker": beat.speaker,
        "text": beat.text,
        "beat_id": uid,
    }


def resume_episode(candidate: Candidate, show: Show) -> int:
    last = candidate.segments[-1]
    episode = show.by_ep[last.ep]
    nxt = last.ep + 1
    if episode.duration - last.end <= 3.0 and nxt in show.by_ep:
        return nxt
    return last.ep


SEVERITY = {"low": 1, "medium": 2, "high": 3}
JUDGE_ALIASES = {"minor_in_danger": "minor"}


def merge_flags(rule_flags: list[str], judge_flags: list[str]) -> list[str]:
    merged: dict[str, str] = {}
    for flag in rule_flags:
        name, _, level = flag.partition(":")
        merged[name] = level or "low"
    for flag in judge_flags:
        name = JUDGE_ALIASES.get(flag.strip().lower(), flag.strip().lower())
        if name not in POLICY:
            continue
        current = merged.get(name)
        if current is None or SEVERITY[current] < SEVERITY["medium"]:
            merged[name] = "medium"
    return [f"{name}:{level}" for name, level in sorted(merged.items(), key=lambda kv: (-SEVERITY[kv[1]], kv[0]))]


def rank_reason(role: str, candidate: Candidate, flags: list[str], landing: int) -> str:
    judge = candidate.judge or {}
    ep = candidate.segments[0].ep
    risky = [f.split(":")[0] for f in flags if f.endswith((":medium", ":high"))]
    scores = {k: judge[k] for k in ("hook", "cliffhanger", "standalone") if isinstance(judge.get(k), (int, float))}
    strengths = [f"{k} {v:g}/5" for k, v in sorted(scores.items(), key=lambda kv: -kv[1]) if v >= 4][:2]
    early = candidate.features.get("series_position", 1.0) <= 0.2
    if role == "control":
        parts = [f"Post first: it sets up the premise from episode {ep}"]
        parts.append("with nothing flagged for ad review" if not risky else f"with only {', '.join(risky)} to clear in ad review")
        parts.append(f"and sends viewers to episode {landing}")
        return " ".join(parts) + "."
    if role == "retargeting":
        return f"Hold for viewers who already started the show: the judge says it gives away a late twist (episode {ep})."
    parts = [f"Test against the control: episode {ep}" + (f", early enough to land viewers on episode {landing}" if early else "")]
    if strengths:
        parts.append(f"strongest on {' and '.join(strengths)}")
    if risky:
        parts.append(f"needs ad review for {', '.join(risky)}")
    if scores.get("standalone", 5) < 3.75:
        parts.append("a stranger may need more context")
    return "; ".join(parts) + "."


def transcript(candidate: Candidate, show: Show) -> list[dict]:
    rows = []
    for seg_index, beat in beats_in(candidate, show):
        if beat.kind not in ("DIALOGUE", "ACTION", "SFX"):
            continue
        rows.append({
            "segment": seg_index + 1,
            "t": round(clip_time(candidate, seg_index, beat.start), 2),
            "kind": beat.kind,
            "speaker": beat.speaker if beat.kind == "DIALOGUE" else "",
            "text": beat.text,
            "hook": beat.uid == candidate.hook_uid,
            "cliffhanger": beat.uid == candidate.cliff_uid,
        })
    return rows


def promo_record(rank: int, candidate: Candidate, show: Show) -> dict:
    judge = candidate.judge or {}
    role = "control" if rank == 1 else "retargeting" if str(judge.get("spoiler_level", "")).lower().startswith("major") else "challenger"
    flags = merge_flags(candidate.policy, judge.get("policy_flags", []))
    landing = resume_episode(candidate, show)
    return {
        "rank": rank,
        "role": role,
        "rank_reason": rank_reason(role, candidate, flags, landing),
        "id": candidate.cid,
        "score": candidate.score,
        "format": candidate.kind,
        "duration": candidate.duration,
        "segments": [
            {
                "episode": s.ep,
                "start": clock(s.start),
                "end": clock(s.end),
                "start_seconds": s.start,
                "end_seconds": s.end,
                "duration": s.duration,
                "episode_duration": show.by_ep[s.ep].duration,
            }
            for s in candidate.segments
        ],
        "transcript": transcript(candidate, show),
        "hook": beat_view(show, candidate.hook_uid),
        "cliffhanger": beat_view(show, candidate.cliff_uid),
        "why_it_works": judge.get("why_it_works") or candidate.why,
        "hook_type": judge.get("hook_type") or candidate.hook_type,
        "arc_position": candidate.arc,
        "spoiler_level": judge.get("spoiler_level", candidate.arc),
        "resume_episode": landing,
        "policy_flags": flags,
        "sound_off_hook": candidate.features.get("sound_off_hook"),
        "judge": {k: v for k, v in judge.items() if k not in ("why_it_works", "hook_type", "policy_flags")},
        "score_parts": candidate.parts,
        "features": candidate.features,
    }


def write_markdown(path: Path, show: Show, records: list[dict], meta: dict):
    out = [f"# Promo shortlist: {show.name}", ""]
    out.append(f"Mode: {meta['mode']} | Model: {meta.get('model') or 'none'} | Episodes: {meta['episodes']} | Candidates scored: {meta['candidates']}")
    out.append("")
    out.append("| Rank | Role | Segments | Length | Type | Arc | Flags |")
    out.append("|---|---|---|---|---|---|---|")
    for r in records:
        segs = " + ".join(f"Ep{s['episode']} {s['start']}-{s['end']}" for s in r["segments"])
        flags = ", ".join(r["policy_flags"]) or "-"
        out.append(f"| {r['rank']} | {r['role']} | {segs} | {r['duration']:.1f}s | {r['hook_type']} | {r['spoiler_level']} | {flags} |")
    out.append("")
    for r in records:
        segs = " + ".join(f"Ep{s['episode']} {s['start']}-{s['end']}" for s in r["segments"])
        out.append(f"## {r['rank']}. {segs} ({r['duration']:.1f}s, {r['format']})")
        out.append(f"- Hook (Ep{r['hook']['episode']} {r['hook']['time']}): {r['hook']['speaker'] + ': ' if r['hook']['speaker'] else ''}{r['hook']['text']}")
        out.append(f"- Cliffhanger (Ep{r['cliffhanger']['episode']} {r['cliffhanger']['time']}): {r['cliffhanger']['speaker'] + ': ' if r['cliffhanger']['speaker'] else ''}{r['cliffhanger']['text']}")
        out.append(f"- Why it works: {r['why_it_works']}")
        out.append(f"- Why this rank: {r['rank_reason']}")
        out.append(f"- Lands viewers on: Episode {r['resume_episode']} | Score: {r['score']}")
        if r["policy_flags"]:
            out.append(f"- Ad policy check: {', '.join(r['policy_flags'])}")
        out.append("")
    path.write_text("\n".join(out), encoding="utf-8")


def write_outputs(out_dir: Path, show: Show, chosen: list[Candidate], scored: list[Candidate], meta: dict, extras: dict):
    out_dir.mkdir(parents=True, exist_ok=True)
    records = [promo_record(i + 1, c, show) for i, c in enumerate(chosen)]
    rejected = [
        {"id": c.cid, "segments": [[s.ep, s.start, s.end] for s in c.segments], "reason": c.judge["rejected"],
         "why_it_works": c.judge.get("why_it_works"), "unexplained_refs": c.judge.get("unexplained_refs")}
        for c in scored if c.judge.get("rejected")
    ]
    payload = {"show": show.name, "meta": meta, "promos": records, "rejected_by_judge": rejected}
    (out_dir / "promos.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(out_dir / "promos.md", show, records, meta)
    with open(out_dir / "promos.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["rank", "role", "rank_reason", "segments", "duration", "hook", "cliffhanger", "why_it_works", "hook_type", "spoiler_level", "resume_episode", "policy_flags", "score"])
        for r in records:
            writer.writerow([
                r["rank"], r["role"], r["rank_reason"],
                " + ".join(f"Ep{s['episode']} {s['start']}-{s['end']}" for s in r["segments"]),
                r["duration"], r["hook"]["text"], r["cliffhanger"]["text"], r["why_it_works"],
                r["hook_type"], r["spoiler_level"], r["resume_episode"], "; ".join(r["policy_flags"]), r["score"],
            ])
    with open(out_dir / "edl.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["promo_rank", "segment", "episode", "source_script", "start", "end", "duration"])
        for r, c in zip(records, chosen):
            for i, s in enumerate(c.segments, 1):
                writer.writerow([r["rank"], i, s.ep, Path(show.by_ep[s.ep].source).name, clock(s.start), clock(s.end), s.duration])
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", 'VIDEO_DIR="${VIDEO_DIR:-./video}"', 'OUT_DIR="${OUT_DIR:-./promo_cuts}"', 'mkdir -p "$OUT_DIR"', ""]
    for r, c in zip(records, chosen):
        tag = f"promo{r['rank']:02d}"
        names = []
        for i, s in enumerate(c.segments, 1):
            name = f"{tag}_part{i}.mp4"
            names.append(name)
            lines.append(f'ffmpeg -y -ss {s.start:.2f} -to {s.end:.2f} -i "$VIDEO_DIR/episode-{s.ep:03d}.mp4" -c:v libx264 -c:a aac "$OUT_DIR/{name}"')
        lines.append(f"printf \"file '%s'\\n\" {' '.join(names)} > \"$OUT_DIR/{tag}.txt\"")
        lines.append(f'ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/{tag}.txt" -c copy "$OUT_DIR/{tag}.mp4"')
        lines.append("")
    (out_dir / "ffmpeg_cuts.sh").write_text("\n".join(lines), encoding="utf-8")
    with open(out_dir / "candidates_scored.jsonl", "w", encoding="utf-8") as fh:
        for c in sorted(scored, key=lambda x: x.score, reverse=True):
            fh.write(json.dumps({
                "id": c.cid, "format": c.kind, "score": c.score, "duration": c.duration,
                "segments": [[s.ep, s.start, s.end] for s in c.segments],
                "hook": c.hook_uid, "cliff": c.cliff_uid, "hook_type": c.hook_type,
                "policy": c.policy, "parts": c.parts, "judge": c.judge,
            }, ensure_ascii=False) + "\n")
    for name, data in extras.items():
        (out_dir / f"{name}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return records
