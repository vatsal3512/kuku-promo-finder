import csv
import json
import re
from itertools import combinations
from pathlib import Path

from .config import load_config
from .parse import load_show, parse_time

SEG_RE = re.compile(r"(?:ep)?\s*(\d+)\s*[: ]\s*([\d:.]+)\s*-\s*([\d:.]+)", re.I)


def parse_segments(text: str) -> list[tuple[int, float, float]]:
    out = []
    for part in re.split(r"[;+|]", text):
        match = SEG_RE.search(part.strip())
        if match:
            out.append((int(match.group(1)), parse_time(match.group(2)), parse_time(match.group(3))))
    return out


def load_run(run_dir: str) -> dict:
    return json.loads((Path(run_dir) / "promos.json").read_text(encoding="utf-8"))


def run_segments(promo: dict) -> list[tuple[int, float, float]]:
    return [(s["episode"], s["start_seconds"], s["end_seconds"]) for s in promo["segments"]]


def load_gold(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("segments", "").strip()]
    for r in rows:
        r["segs"] = parse_segments(r["segments"])
    return [r for r in rows if r["segs"]]


def iou(a: list[tuple], b: list[tuple]) -> float:
    inter = 0.0
    for ea, sa, xa in a:
        for eb, sb, xb in b:
            if ea == eb:
                inter += max(0.0, min(xa, xb) - max(sa, sb))
    total = sum(x - s for _, s, x in a) + sum(x - s for _, s, x in b) - inter
    return inter / total if total > 0 else 0.0


def gold_metrics(run: dict, gold: list[dict], threshold: float = 0.5) -> dict:
    promos = run["promos"]
    best = []
    for p in promos:
        scores = [iou(run_segments(p), g["segs"]) for g in gold]
        best.append(max(scores) if scores else 0.0)
    hits = [b >= threshold for b in best]

    def precision(k):
        top = hits[:k]
        return round(sum(top) / len(top), 3) if top else 0.0

    covered = 0
    for g in gold:
        if any(iou(run_segments(p), g["segs"]) >= threshold for p in promos):
            covered += 1
    first = next((i + 1 for i, h in enumerate(hits) if h), None)
    return {
        "threshold": threshold,
        "promos": len(promos),
        "gold": len(gold),
        "precision_at_5": precision(5),
        "precision_at_10": precision(10),
        "recall_of_gold": round(covered / len(gold), 3) if gold else 0.0,
        "mean_best_iou": round(sum(best) / len(best), 3) if best else 0.0,
        "reciprocal_rank": round(1 / first, 3) if first else 0.0,
        "per_promo_best_iou": [round(b, 3) for b in best],
    }


def validity(run: dict, input_path: str, config_path: str | None = None) -> dict:
    cfg = load_config(config_path)
    g = cfg["gates"]
    show = load_show(input_path)
    issues = []
    for p in run["promos"]:
        rank = p["rank"]
        if not g["min_duration"] <= p["duration"] <= g["max_duration"]:
            issues.append(f"#{rank} duration {p['duration']}")
        if len(p["segments"]) > g["max_segments"]:
            issues.append(f"#{rank} too many segments")
        hook = show.beats.get(p["hook"]["beat_id"])
        first = p["segments"][0]
        if hook is None or hook.text != p["hook"]["text"]:
            issues.append(f"#{rank} hook text not found in script")
        elif not 0 <= hook.start - first["start_seconds"] <= g["max_hook_offset"]:
            issues.append(f"#{rank} hook starts {hook.start - first['start_seconds']:.2f}s in")
        for s in p["segments"]:
            episode = show.by_ep.get(s["episode"])
            if episode is None:
                issues.append(f"#{rank} unknown episode {s['episode']}")
                continue
            if not 0 <= s["start_seconds"] < s["end_seconds"] <= episode.duration + 0.01:
                issues.append(f"#{rank} segment outside episode")
            for cut in (s["start_seconds"], s["end_seconds"]):
                if any(b.start + 0.05 < cut < b.end - 0.05 for b in episode.lines):
                    issues.append(f"#{rank} cut at {cut} splits a line")
    return {"checked": len(run["promos"]), "issues": issues, "all_valid": not issues}


def kendall(a: list, b: list) -> float:
    pairs = list(combinations(range(len(a)), 2))
    if not pairs:
        return 0.0
    score = 0
    for i, j in pairs:
        x = a[i] - a[j]
        y = b[i] - b[j]
        score += 1 if x * y > 0 else -1 if x * y < 0 else 0
    return round(score / len(pairs), 3)


def compare_runs(run_a: dict, run_b: dict, k: int = 10, threshold: float = 0.5) -> dict:
    top_a, top_b = run_a["promos"][:k], run_b["promos"][:k]
    matches = []
    used = set()
    for p in top_a:
        best_j, best = None, 0.0
        for j, q in enumerate(top_b):
            if j in used:
                continue
            score = iou(run_segments(p), run_segments(q))
            if score > best:
                best_j, best = j, score
        if best_j is not None and best >= threshold:
            used.add(best_j)
            matches.append((p["rank"], top_b[best_j]["rank"]))
    return {
        "k": k,
        "shared_in_top_k": len(matches),
        "overlap_ratio": round(len(matches) / k, 3) if k else 0.0,
        "kendall_tau_on_shared": kendall([m[0] for m in matches], [m[1] for m in matches]) if len(matches) > 1 else None,
        "pairs": matches,
    }


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None

    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            for t in range(i, j + 1):
                out[order[t]] = (i + j) / 2 + 1
            i = j + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    return round(cov / (vx * vy), 3) if vx and vy else None


def judge_agreement(run_dir: str, human_csv: str) -> dict:
    judged = {}
    with open(Path(run_dir) / "candidates_scored.jsonl", encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if row.get("judge"):
                judged[row["id"]] = row["judge"]
    with open(human_csv, encoding="utf-8") as fh:
        human = list(csv.DictReader(fh))
    out = {}
    for field in ("hook", "cliffhanger", "standalone", "overall"):
        xs, ys = [], []
        for row in human:
            j = judged.get(row.get("id", ""))
            if not j or not row.get(field):
                continue
            value = j.get("judge_score") * 5 if field == "overall" else j.get(field)
            if value is None:
                continue
            xs.append(float(row[field]))
            ys.append(float(value))
        out[field] = {"n": len(xs), "spearman": spearman(xs, ys)}
    return out


def report(run_dir: str, input_path: str, gold_path: str | None, config_path: str | None = None) -> dict:
    run = load_run(run_dir)
    result = {"run": run_dir, "mode": run["meta"]["mode"], "model": run["meta"].get("model"), "validity": validity(run, input_path, config_path)}
    if gold_path and Path(gold_path).exists():
        gold = load_gold(gold_path)
        result["gold_iou_0.5"] = gold_metrics(run, gold, 0.5)
        result["gold_iou_0.3"] = gold_metrics(run, gold, 0.3)
    return result
