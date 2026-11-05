from .config import merge

PROFILES = {
    "fast": {
        "about": "about 5 minutes for 50 episodes: quick tagging without model reasoning, one judging pass on 30 clips, no second judge, no refinement",
        "skip_bible": True,
        "llm": {"judge_pool": 30, "judge_repeats": 1, "refine_seeds": 0, "jury_model": "", "pairwise_top": 0, "learned_wave": 0, "concurrency": 10,
                "tag_extra": {"chat_template_kwargs": {"enable_thinking": False}}},
    },
    "standard": {
        "about": "about 10 minutes: two judging passes on 60 clips, light refinement, no second judge",
        "llm": {"judge_pool": 60, "judge_repeats": 2, "refine_seeds": 10, "jury_model": "", "pairwise_top": 8, "learned_wave": 0},
    },
    "full": {
        "about": "20-25 minutes: everything in the config, including the second judge",
    },
}


def apply_profile(cfg: dict, name: str | None) -> dict:
    if not name:
        return cfg
    if name not in PROFILES:
        raise ValueError(f"Unknown profile {name!r}. Use one of: {', '.join(PROFILES)}")
    extra = {k: v for k, v in PROFILES[name].items() if k not in ("about", "skip_bible")}
    out = merge(cfg, extra)
    out["profile"] = name
    out["skip_bible"] = bool(PROFILES[name].get("skip_bible"))
    return out
