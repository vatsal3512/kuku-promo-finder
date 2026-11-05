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
from .rank import base_score, craft_check, pick_control, select
from .rules import score_beats


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "show"


def run(input_path: str, out_root: str = "outputs", mode: str = "offline", model: str | None = None,
        config_path: str | None = None, top: int | None = None, name: str | None = None,
        judge_model: str | None = None, jury_model: str | None = None, log=print) -> dict:
    started = time.time()
    cfg = load_config(config_path)
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

    bible = None
    learn_info = None
    llm = None
    if mode == "llm":
        from .bible import build_bible
        from .llm import LLM
        llm = LLM(cfg["llm"]["model"], cfg["llm"])
        bible = build_bible(show, llm, log)
        cfg["names"] = list(cfg.get("names") or []) + bible.get("aliases", [])
    mapping = apply_names(show, cfg.get("names"))

    priors = score_beats(show)
    tag_report = None
    if mode == "llm":
        from .tag import tag_show
        tag_report = tag_show(show, priors, llm, cfg, log)

    candidates = generate(show, priors, cfg)
    log(f"Generated {len(candidates)} candidate windows")
    scored = []
    for c in candidates:
        featurize(c, show, priors)
        if gates_pass(c, cfg):
            c.score = base_score(c, cfg)
            scored.append(c)
    log(f"{len(scored)} passed the hard gates")
    if mode != "llm":
        for c in scored:
            craft = craft_check(c, cfg)
            if craft:
                c.parts["craft"] = -round(sum(craft.values()), 4)
                c.judge["craft"] = craft
                c.score = round(c.score - sum(craft.values()), 4)

    if mode == "llm":
        from .judge import judge_show
        _, learn_info = judge_show(show, scored, llm, cfg, log)

    eligible = [c for c in scored if not c.judge.get("rejected")]
    jury_info = None
    if mode == "llm":
        from .judge import jury_check
        jury_info = jury_check(show, eligible, cfg, log)
        eligible = [c for c in eligible if not c.judge.get("rejected")]
    chosen = select(eligible, cfg)
    if mode == "llm" and cfg["llm"].get("pairwise_top"):
        from .judge import pairwise_order
        chosen = pairwise_order(show, chosen, llm, cfg, log)
    chosen = pick_control(chosen, cfg)

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
    log(f"Wrote {len(records)} promos to {out_dir}")
    return {"out_dir": str(out_dir), "records": records, "meta": meta}
