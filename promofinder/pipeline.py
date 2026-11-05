import re
import time
from datetime import datetime
from pathlib import Path

from .candidates import generate
from .config import load_config
from .export import write_outputs
from .features import featurize, gates_pass
from .names import apply_names, label_drift, place_drift
from .parse import load_show
from .profiles import apply_profile
from .rank import base_score, craft_check, pick_control, select
from .rules import score_beats


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "show"


def run(input_path: str, out_root: str = "outputs", mode: str = "offline", model: str | None = None,
        config_path: str | None = None, top: int | None = None, name: str | None = None,
        judge_model: str | None = None, jury_model: str | None = None, profile: str | None = None, log=print) -> dict:
    started = time.time()
    cfg = apply_profile(load_config(config_path), profile)
    if top:
        cfg["selection"]["top"] = top
    if model:
        cfg["llm"]["model"] = model
    if judge_model:
        cfg["llm"]["judge_model"] = judge_model
    if jury_model:
        cfg["llm"]["jury_model"] = "" if jury_model.lower() == "none" else jury_model
    show = load_show(input_path, name)
    if not show.episodes:
        raise SystemExit(f"No screenplay episodes found in {input_path}")
    log(f"Parsed {len(show.episodes)} episodes, {len(show.beats)} beats")

    degraded: list[dict] = []
    steps = 6 if mode == "llm" else 3

    def step(n: int, text: str):
        log(f"[{n}/{steps}] {text}")

    def guarded(stage: str, fn, fallback=None):
        nonlocal llm
        if llm is not None and llm.dead:
            degraded.append({"stage": stage, "reason": str(llm.dead)})
            return fallback
        try:
            return fn()
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"[:300]
            log(f"WARNING: {stage} failed, continuing with rules for this step ({reason})")
            degraded.append({"stage": stage, "reason": reason})
            return fallback

    bible = None
    learn_info = None
    llm = None
    if mode == "llm":
        from .llm import LLM
        try:
            llm = LLM(cfg["llm"]["model"], cfg["llm"])
            if not hasattr(llm, "dead"):
                llm.dead = None
        except Exception as exc:
            log(f"WARNING: model unavailable ({exc}). Running with rules only.")
            degraded.append({"stage": "model", "reason": str(exc)[:300]})
            mode = "offline"
            steps = 3
    if mode == "llm" and not cfg.get("skip_bible"):
        from .bible import build_bible
        step(1, "Reading the whole show for character names")
        bible = guarded("series bible", lambda: build_bible(show, llm, log))
        if bible:
            cfg["names"] = list(cfg.get("names") or []) + bible.get("aliases", [])
    mapping = apply_names(show, cfg.get("names"))

    priors = score_beats(show)
    tag_report = None
    if mode == "llm":
        from .tag import tag_show
        step(2, f"Asking the model for the best hooks and cliffhangers in {len(show.episodes)} episodes")
        tag_report = guarded("tagging", lambda: tag_show(show, priors, llm, cfg, log))
        if llm.dead:
            log(f"WARNING: model stopped working ({llm.dead}). Finishing with rules only.")

    step(3 if mode == "llm" else 1, "Building possible clips")
    candidates = generate(show, priors, cfg)
    log(f"Generated {len(candidates)} candidate windows")
    scored = []
    for c in candidates:
        featurize(c, show, priors)
        if gates_pass(c, cfg):
            c.score = base_score(c, cfg)
            scored.append(c)
    log(f"{len(scored)} passed the hard gates")
    if mode != "llm" or llm.dead:
        for c in scored:
            craft = craft_check(c, cfg)
            if craft:
                c.parts["craft"] = -round(sum(craft.values()), 4)
                c.judge["craft"] = craft
                c.score = round(c.score - sum(craft.values()), 4)

    if mode == "llm" and not llm.dead:
        from .judge import judge_show
        step(4, "Judging the strongest clips as a first-time viewer")
        judged = guarded("judging", lambda: judge_show(show, scored, llm, cfg, log))
        learn_info = judged[1] if judged else None

    eligible = [c for c in scored if not c.judge.get("rejected")]
    jury_info = None
    if mode == "llm" and cfg["llm"].get("jury_model"):
        from .judge import jury_check
        step(5, "Second model double-checks the shortlist")
        jury_info = guarded("second judge", lambda: jury_check(show, eligible, cfg, log))
        eligible = [c for c in eligible if not c.judge.get("rejected")]
    if not eligible and scored:
        log("WARNING: every clip was rejected by the judge. Falling back to the rule ranking.")
        degraded.append({"stage": "selection", "reason": "all judged clips rejected"})
        eligible = scored
    chosen = select(eligible, cfg)
    if mode == "llm" and cfg["llm"].get("pairwise_top") and not llm.dead:
        from .judge import pairwise_order
        step(6, "Ordering the final list")
        chosen = guarded("ordering", lambda: pairwise_order(show, chosen, llm, cfg, log), chosen) or chosen
    chosen = pick_control(chosen, cfg)
    if not chosen:
        log("No promo fits the rules (20-60 s, hook in the first 3 s, clean cliffhanger cut). See the check command for why.")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(out_root) / slug(show.name) / f"{stamp}-{mode}"
    meta = {
        "show": show.name,
        "input": str(input_path),
        "mode": mode,
        "model": cfg["llm"]["model"] if mode == "llm" else None,
        "judge_model": (cfg["llm"].get("judge_model") or cfg["llm"]["model"]) if mode == "llm" else None,
        "episodes": len(show.episodes),
        "beats": len(show.beats),
        "candidates": len(scored),
        "generated": len(candidates),
        "seconds": round(time.time() - started, 2),
        "llm_usage": llm.usage() if llm else None,
        "profile": cfg.get("profile"),
        "degraded": degraded,
        "config": cfg,
    }
    extras = {
        "names_map": mapping,
        "name_drift": {"places_and_names": place_drift(show), "speaker_labels": label_drift(mapping)},
    }
    if bible:
        extras["series_bible"] = bible
    if tag_report is not None:
        extras["episode_tags"] = tag_report
    if learn_info:
        extras["judge_predictor"] = learn_info
    if jury_info and jury_info.get("used"):
        extras["jury"] = jury_info
    records = write_outputs(out_dir, show, chosen, scored, meta, extras)
    meta["seconds"] = round(time.time() - started, 2)
    step(steps, f"Wrote {len(records)} promos to {out_dir}")
    if degraded:
        log(f"Note: {len(degraded)} step(s) fell back to rules: " + "; ".join(d["stage"] for d in degraded))
    return {"out_dir": str(out_dir), "records": records, "meta": meta}
