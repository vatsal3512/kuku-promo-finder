import argparse
import json
import sys

from .pipeline import run


def print_promos(records):
    for r in records:
        segs = " + ".join(f"Ep{s['episode']} {s['start']}-{s['end']}" for s in r["segments"])
        print(f"{r['rank']:>2}. {segs:<46} {r['duration']:>5.1f}s  {r['hook_type']:<13} {r['hook']['text'][:60]}")


def main(argv=None):
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="promofinder", allow_abbrev=False, description="Find ranked promo clips in microdrama screenplays.")
    sub = parser.add_subparsers(dest="command", required=True)

    go = sub.add_parser("run", allow_abbrev=False, help="Run the pipeline on a folder of episode scripts")
    go.add_argument("--input", required=True, help="Folder (or single file) of episode screenplays")
    go.add_argument("--out", default="outputs", help="Output root folder")
    go.add_argument("--offline", action="store_true", help="Rules only, no LLM calls")
    go.add_argument("--model", default=None, help="provider/model, e.g. groq/llama-3.3-70b-versatile")
    go.add_argument("--judge-model", default=None, help="Optional different model for judging")
    go.add_argument("--jury-model", default=None, help="Second model that must also pass the shortlist as standalone; 'none' turns it off")
    go.add_argument("--config", default="config.yaml", help="YAML config with weights and gates")
    go.add_argument("--top", type=int, default=None, help="Number of promos to return")
    go.add_argument("--name", default=None, help="Show name for the report")
    go.add_argument("--profile", choices=["fast", "standard", "full"], default=None, help="fast: about 5 min, standard: about 10 min, full: everything in the config")

    chk = sub.add_parser("check", allow_abbrev=False, help="Show how an input parses before spending any LLM calls")
    chk.add_argument("--input", required=True)
    chk.add_argument("--verbose", action="store_true", help="Also list every episode")
    chk.add_argument("--model", default=None, help="Also test this provider/model: key, speed and JSON replies")
    chk.add_argument("--config", default="config.yaml")

    ev = sub.add_parser("eval", allow_abbrev=False, help="Check a run for validity and score it against a gold set")
    ev.add_argument("--run", required=True)
    ev.add_argument("--input", required=True)
    ev.add_argument("--gold", default=None)
    ev.add_argument("--config", default="config.yaml")

    cmp = sub.add_parser("compare", allow_abbrev=False, help="Agreement between two runs")
    cmp.add_argument("run_a")
    cmp.add_argument("run_b")
    cmp.add_argument("--k", type=int, default=10)

    agree = sub.add_parser("agree", allow_abbrev=False, help="Spearman between judge scores and your own scores")
    agree.add_argument("--run", required=True)
    agree.add_argument("--human", required=True)

    base = sub.add_parser("baseline", allow_abbrev=False, help="Ablation: ask the model for promo timestamps directly, then validate them")
    base.add_argument("--input", required=True)
    base.add_argument("--model", default=None)
    base.add_argument("--episodes", default="", help="Comma list, e.g. 1,2,3. Empty means all")
    base.add_argument("--out", default="outputs/baseline_llm_only.json")
    base.add_argument("--config", default="config.yaml")

    au = sub.add_parser("audit", allow_abbrev=False, help="Blind re-judge the top promos of several runs with a held-out model")
    au.add_argument("runs", nargs="+")
    au.add_argument("--input", required=True)
    au.add_argument("--model", required=True)
    au.add_argument("--top", type=int, default=15)
    au.add_argument("--out", default=None)
    au.add_argument("--config", default="config.yaml")
    au.add_argument("--batch", type=int, default=None, help="Clips per judge call")
    au.add_argument("--concurrency", type=int, default=None, help="Parallel judge calls")

    args = parser.parse_args(argv)
    if args.command == "run":
        result = run(
            args.input,
            out_root=args.out,
            mode="offline" if args.offline else "llm",
            model=args.model,
            judge_model=args.judge_model,
            jury_model=args.jury_model,
            config_path=args.config,
            top=args.top,
            name=args.name,
            profile=args.profile,
        )
        print_promos(result["records"])
        if result["meta"].get("degraded"):
            print()
            print("Some steps fell back to rules: " +"; ".join(f"{d['stage']} ({d['reason'][:80]})" for d in result["meta"]["degraded"]))
    elif args.command == "check":
        from .doctor import check_input, probe_model
        result = check_input(args.input)
        if not args.verbose:
            result.pop("per_episode", None)
        if args.model:
            from .config import load_config
            result["model"] = probe_model(args.model, load_config(args.config)["llm"])
        print(json.dumps(result, indent=2))
        if not result.get("ok") or (args.model and not result["model"]["ok"]):
            sys.exit(1)
    elif args.command == "eval":
        from .evaluate import report
        print(json.dumps(report(args.run, args.input, args.gold, args.config), indent=2))
    elif args.command == "compare":
        from .evaluate import compare_runs, load_run
        print(json.dumps(compare_runs(load_run(args.run_a), load_run(args.run_b), args.k), indent=2))
    elif args.command == "baseline":
        from .baseline import run_baseline
        from .config import load_config
        cfg = load_config(args.config)
        episodes = [int(x) for x in args.episodes.split(",") if x.strip()]
        print(json.dumps(run_baseline(args.input, args.model or cfg["llm"]["model"], episodes, args.out, cfg), indent=2))
    elif args.command == "audit":
        from .audit import audit
        from .config import load_config
        audit_cfg = load_config(args.config)
        if args.batch:
            audit_cfg["llm"]["judge_batch"] = args.batch
        if args.concurrency:
            audit_cfg["llm"]["concurrency"] = args.concurrency
        print(json.dumps(audit(args.runs, args.input, args.model, audit_cfg, args.top, args.out, log=lambda m: print(m, file=sys.stderr)), indent=2))
    elif args.command == "agree":
        from .evaluate import judge_agreement
        print(json.dumps(judge_agreement(args.run, args.human), indent=2))


if __name__ == "__main__":
    main()
