import json
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from promofinder.judge import render_clip
from promofinder.models import Candidate, Segment
from promofinder.names import apply_names
from promofinder.parse import load_show
from promofinder.pipeline import run

ROOT = Path(__file__).parent
OUTPUTS = ROOT / "outputs"
SAMPLE = ROOT / "tests" / "fixtures" / "sample_show"

st.set_page_config(page_title="PromoFinder", layout="wide")
st.title("PromoFinder")
st.caption("Ranked 20-60s promo cuts from microdrama screenplays. The model picks moments, code computes every timestamp.")


def list_runs():
    if not OUTPUTS.exists():
        return []
    return sorted((p for p in OUTPUTS.glob("*/*") if (p / "promos.json").exists()), key=lambda p: p.name, reverse=True)


with st.sidebar:
    st.header("New run")
    uploads = st.file_uploader("Episode scripts (.txt)", type=["txt"], accept_multiple_files=True)
    use_sample = st.checkbox("Use the bundled sample show", value=not uploads)
    mode = st.radio("Mode", ["offline", "llm"], horizontal=True)
    model = st.text_input("Model (provider/model)", "nvidia/nvidia/nemotron-3-ultra-550b-a55b", disabled=mode == "offline")
    top = st.slider("Promos to return", 5, 25, 15)
    if st.button("Run", type="primary"):
        work = Path(tempfile.mkdtemp(prefix="promofinder-"))
        if uploads and not use_sample:
            for f in uploads:
                (work / f.name).write_bytes(f.getvalue())
            source = work
        else:
            source = SAMPLE
        logs = []
        with st.spinner("Running"):
            try:
                result = run(str(source), out_root=str(OUTPUTS), mode=mode, model=model if mode == "llm" else None, top=top, log=logs.append)
                st.session_state["run_dir"] = result["out_dir"]
                st.session_state["source"] = str(source)
                st.success(f"Done in {result['meta']['seconds']}s")
            except Exception as exc:
                st.error(str(exc))
        if logs:
            st.code("\n".join(logs[-15:]))
    st.header("Open a run")
    runs = list_runs()
    if runs:
        labels = [str(p.relative_to(OUTPUTS)) for p in runs]
        current = st.session_state.get("run_dir")
        index = next((i for i, p in enumerate(runs) if str(p) == current), 0)
        picked = st.selectbox("Run", labels, index=index)
        st.session_state["run_dir"] = str(OUTPUTS / picked)

run_dir = st.session_state.get("run_dir")
if not run_dir:
    st.info("Run the sample show or upload scripts to begin.")
    st.stop()

payload = json.loads((Path(run_dir) / "promos.json").read_text(encoding="utf-8"))
meta = payload["meta"]
promos = payload["promos"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Episodes", meta["episodes"])
c2.metric("Candidates scored", meta["candidates"])
c3.metric("Mode", meta["mode"])
usage = meta.get("llm_usage") or {}
c4.metric("LLM calls (new + cached)", f"{usage.get('calls', 0)} + {usage.get('cache_hits', 0)}")

show = None
source = meta.get("input")
if source and Path(source).exists():
    show = load_show(source, payload["show"])
    apply_names(show, meta["config"].get("names"))

types = sorted({p["hook_type"] for p in promos})
arcs = sorted({p["spoiler_level"] for p in promos})
f1, f2, f3 = st.columns(3)
type_filter = f1.multiselect("Hook type", types, default=types)
arc_filter = f2.multiselect("Spoiler level", arcs, default=arcs)
safe_only = f3.checkbox("Hide promos with high policy risk")

feedback_path = Path(run_dir) / "feedback.jsonl"
table = []
for p in promos:
    if p["hook_type"] not in type_filter or p["spoiler_level"] not in arc_filter:
        continue
    if safe_only and any(f.endswith(":high") for f in p["policy_flags"]):
        continue
    table.append(p)

st.dataframe(pd.DataFrame([{
    "rank": p["rank"],
    "segments": " + ".join(f"Ep{s['episode']} {s['start']}-{s['end']}" for s in p["segments"]),
    "length": f"{p['duration']:.1f}s",
    "type": p["hook_type"],
    "spoiler": p["spoiler_level"],
    "lands on": f"Ep{p['resume_episode']}",
    "flags": ", ".join(p["policy_flags"]),
    "score": p["score"],
} for p in table]), hide_index=True, width="stretch")

for p in table:
    segs = " + ".join(f"Ep{s['episode']} {s['start']}-{s['end']}" for s in p["segments"])
    with st.expander(f"#{p['rank']} {p.get('role', '')}  {segs}  ({p['duration']:.1f}s, {p['hook_type']})"):
        left, right = st.columns([3, 2])
        with left:
            st.markdown(f"**Hook** (Ep{p['hook']['episode']} {p['hook']['time']}): {p['hook']['speaker'] + ': ' if p['hook']['speaker'] else ''}{p['hook']['text']}")
            st.markdown(f"**Cliffhanger** (Ep{p['cliffhanger']['episode']} {p['cliffhanger']['time']}): {p['cliffhanger']['speaker'] + ': ' if p['cliffhanger']['speaker'] else ''}{p['cliffhanger']['text']}")
            st.markdown(f"**Why it works:** {p['why_it_works']}")
            if show:
                cand = Candidate(p["id"], p["format"], [Segment(s["episode"], s["start_seconds"], s["end_seconds"]) for s in p["segments"]], p["hook"]["beat_id"], p["cliffhanger"]["beat_id"])
                st.code(render_clip(cand, show), language=None)
        with right:
            judge = p.get("judge") or {}
            if judge:
                st.write({k: judge[k] for k in ("hook", "cliffhanger", "standalone", "escalation", "premise") if k in judge})
                if judge.get("open_question"):
                    st.markdown(f"**Open question:** {judge['open_question']}")
                if judge.get("unexplained_refs"):
                    st.markdown(f"**Needs context:** {', '.join(judge['unexplained_refs'])}")
                jury = judge.get("jury") or {}
                if "standalone" in jury:
                    st.markdown(f"**Second model** ({jury.get('model', '').split('/')[-1]}): " + ", ".join(f"{k} {jury[k]:g}" for k in ("hook", "cliffhanger", "standalone") if k in jury))
                if judge.get("spoiler_note"):
                    st.caption(judge["spoiler_note"])
            st.markdown(f"**Ad policy:** {', '.join(p['policy_flags']) or 'nothing flagged'}  \n**Lands viewers on:** episode {p['resume_episode']}  \n**Spoiler level:** {p['spoiler_level']}")
            st.write(p["score_parts"])
            note = st.text_input("Note", key=f"note-{p['id']}")
            a, r = st.columns(2)
            for col, verdict in ((a, "approve"), (r, "reject")):
                if col.button(verdict.capitalize(), key=f"{verdict}-{p['id']}"):
                    with open(feedback_path, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps({"id": p["id"], "rank": p["rank"], "verdict": verdict, "note": note, "at": datetime.now().isoformat(timespec="seconds")}) + "\n")
                    st.toast(f"Saved {verdict} for #{p['rank']}")
