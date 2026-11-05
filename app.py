import base64
import html
import json
import os
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from promofinder.parse import SCRIPT_SUFFIXES
from promofinder.pipeline import run

ROOT = Path(__file__).parent
OUTPUTS = ROOT / "outputs"
RAW = ROOT / "raw_outputs"
SAMPLE = ROOT / "tests" / "fixtures" / "sample_show"
LOGO = ROOT / "assets" / "kuku-logo-white.png"
CONFIG = ROOT / "config.yaml"
RED = "#EC1C24"
MAX_PUBLIC_EPISODES = 60
MODES = {
    "fast": ("Fast", "AI picks and one judging pass, about 5 minutes for 50 episodes"),
    "offline": ("Rules only", "no AI, a few seconds, no key needed"),
    "full": ("Full", "everything including the second judge, 20-25 minutes, needs the passcode"),
}


def secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, "") or os.environ.get(name, ""))
    except Exception:
        return os.environ.get(name, "")


def unpack(uploads, work: Path) -> list[str]:
    names = []
    for f in uploads:
        if f.name.lower().endswith(".zip"):
            with zipfile.ZipFile(f) as zf:
                for info in zf.infolist():
                    inner = Path(info.filename)
                    if info.is_dir() or inner.suffix.lower() not in SCRIPT_SUFFIXES or inner.name.startswith("."):
                        continue
                    target = work / inner.name
                    n = 2
                    while target.exists():
                        target = work / f"{inner.stem} ({n}){inner.suffix}"
                        n += 1
                    target.write_bytes(zf.read(info))
                    names.append(inner.name)
        else:
            (work / Path(f.name).name).write_bytes(f.getvalue())
            names.append(f.name)
    return names

st.set_page_config(page_title="PromoFinder", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Figtree:ital,wght@0,400;0,500;0,600;0,700;1,400&family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&display=swap');
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button { font-family: 'Figtree', sans-serif; }
.stApp { background: #0E0F11; }
#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 3.2rem; padding-bottom: 2rem; max-width: 1280px; }
section[data-testid="stSidebar"] { background: #131416; border-right: 1px solid #222327; }
.bar { display: flex; align-items: center; justify-content: space-between; padding-bottom: 12px; border-bottom: 1px solid #222327; margin-bottom: 14px; }
.brand { display: flex; align-items: center; gap: 12px; }
.brand img { height: 22px; }
.brand .slash { color: #45474d; font-size: 20px; }
.brand .app { font-family: 'Bricolage Grotesque', sans-serif; font-weight: 700; font-size: 19px; color: #fff; letter-spacing: -0.2px; }
.show { font-size: 13px; color: #9a9da3; text-align: right; line-height: 1.4; }
.show b { color: #ededed; font-weight: 600; }
.label { font-size: 11.5px; letter-spacing: 0.9px; text-transform: uppercase; color: #8a8d93; margin: 18px 0 6px 0; }
.title { font-family: 'Bricolage Grotesque', sans-serif; font-weight: 700; font-size: 26px; color: #fff; letter-spacing: -0.4px; margin: 2px 0 2px 0; }
.meta { color: #9a9da3; font-size: 14px; }
.meta .first { color: #EC1C24; font-weight: 600; }
.meta .retarget { color: #d9a43a; font-weight: 600; }
.quote { font-size: 17px; color: #f2f2f2; line-height: 1.4; margin: 2px 0 0 0; }
.quote .at { display: block; color: #7d8086; font-size: 12.5px; margin-top: 2px; }
.text { color: #c9cbcf; font-size: 14.5px; line-height: 1.5; }
.warn { color: #e8b4b6; font-size: 14px; line-height: 1.5; }
.tl { margin: 6px 0 2px 0; }
.tl .cap { font-size: 12px; color: #8a8d93; margin: 6px 0 3px 0; }
.lines { border-top: 1px solid #222327; margin-top: 4px; }
.ln { display: grid; grid-template-columns: 42px 1fr; gap: 10px; padding: 6px 0 6px 10px; border-bottom: 1px solid #1b1c1f; font-size: 14px; line-height: 1.45; border-left: 2px solid transparent; }
.ln.key { border-left-color: #EC1C24; background: #17181b; }
.ln .t { color: #6f7278; font-variant-numeric: tabular-nums; font-size: 12.5px; padding-top: 1px; }
.ln .who { color: #ededed; font-weight: 600; margin-right: 6px; }
.ln .act { color: #9a9da3; font-style: italic; }
.ln .tag { color: #EC1C24; font-size: 11px; font-weight: 700; letter-spacing: 0.6px; text-transform: uppercase; margin-left: 8px; }
.cut { color: #6f7278; font-size: 11.5px; letter-spacing: 1px; text-transform: uppercase; padding: 6px 0 6px 10px; border-bottom: 1px solid #1b1c1f; }
.scores { color: #9a9da3; font-size: 13.5px; }
.scores b { color: #ededed; font-weight: 600; }
.guide { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px 28px; padding: 4px 2px 2px 2px; }
.guide .n { display: inline-block; width: 20px; height: 20px; border-radius: 50%; border: 1px solid #EC1C24; color: #EC1C24; font-size: 12px; font-weight: 700; text-align: center; line-height: 18px; margin-right: 8px; }
.guide .h { color: #ededed; font-weight: 600; font-size: 14.5px; }
.guide .b { color: #a9acb2; font-size: 13.5px; line-height: 1.5; margin: 4px 0 0 28px; }
.guide .b b { color: #dcdcdc; font-weight: 600; }
.foot { color: #6f7278; font-size: 12px; margin-top: 28px; padding-top: 10px; border-top: 1px solid #222327; }
.foot a { color: #9a9da3; }
.stButton button { border-radius: 6px; font-weight: 600; }
.stButton button[kind="primary"] { background: #EC1C24; border-color: #EC1C24; }
div[data-testid="stDataFrame"] { border: 1px solid #222327; border-radius: 6px; }
</style>
""",
    unsafe_allow_html=True,
)


def esc(text) -> str:
    return html.escape(str(text or ""))


def logo() -> str:
    if not LOGO.exists():
        return '<span class="app">kuku</span>'
    return f'<img src="data:image/png;base64,{base64.b64encode(LOGO.read_bytes()).decode()}" alt="kuku">'


def list_runs() -> list[Path]:
    fresh = sorted((p for p in OUTPUTS.glob("*/*") if (p / "promos.json").exists()), key=lambda p: p.name, reverse=True) if OUTPUTS.exists() else []
    shipped = [RAW / n for n in ("final_run", "rules_only_run") if (RAW / n / "promos.json").exists()]
    return fresh + shipped


def run_name(p: Path) -> str:
    if p.parent == RAW:
        return {"final_run": "Submitted run, full input pack", "rules_only_run": "Rules only, full input pack"}.get(p.name, p.name)
    stamp = p.name.split("-")
    when = f"{stamp[1][:2]}:{stamp[1][2:4]}" if len(stamp) > 1 and len(stamp[1]) >= 4 else p.name
    return f"{p.parent.name.replace('-', ' ')}, {stamp[-1]} run at {when}"


def mmss(t: float) -> str:
    return f"{int(t // 60)}:{int(t % 60):02d}"


def timeline(p: dict) -> str:
    rows = []
    width = 100.0
    for i, s in enumerate(p["segments"]):
        total = s.get("episode_duration") or max(s["end_seconds"], 1)
        a = s["start_seconds"] / total * width
        b = s["end_seconds"] / total * width
        hook_end = min(b, (s["start_seconds"] + 3) / total * width) if i == 0 else a
        rows.append(
            f'<div class="cap">Episode {s["episode"]} &nbsp;·&nbsp; cut {s["start"]} to {s["end"]} of {mmss(total)}</div>'
            f'<svg width="100%" height="14" viewBox="0 0 100 14" preserveAspectRatio="none">'
            f'<rect x="0" y="5" width="100" height="4" rx="2" fill="#26272b"/>'
            f'<rect x="{a:.2f}" y="3" width="{max(b - a, 0.6):.2f}" height="8" rx="2" fill="#7a1418"/>'
            f'<rect x="{a:.2f}" y="3" width="{max(hook_end - a, 0):.2f}" height="8" rx="2" fill="{RED}"/>'
            f"</svg>"
        )
    return '<div class="tl">' + "".join(rows) + "</div>"


def transcript(p: dict) -> str:
    lines = p.get("transcript") or []
    if not lines:
        return '<div class="text">The transcript is saved with runs made by this version of the tool.</div>'
    out, seg = [], lines[0]["segment"]
    for ln in lines:
        if ln["segment"] != seg:
            out.append('<div class="cut">cut to next segment</div>')
            seg = ln["segment"]
        tag = ' <span class="tag">hook</span>' if ln["hook"] else ' <span class="tag">cliffhanger</span>' if ln["cliffhanger"] else ""
        body = f'<span class="who">{esc(ln["speaker"])}</span>{esc(ln["text"])}' if ln["kind"] == "DIALOGUE" else f'<span class="act">{esc(ln["text"])}</span>'
        key = " key" if ln["hook"] or ln["cliffhanger"] else ""
        out.append(f'<div class="ln{key}"><div class="t">{mmss(ln["t"])}</div><div>{body}{tag}</div></div>')
    return '<div class="lines">' + "".join(out) + "</div>"


def said(beat: dict) -> str:
    who = f'{esc(beat["speaker"])}: ' if beat.get("speaker") else ""
    return f'{who}&ldquo;{esc(beat["text"])}&rdquo;' if beat.get("kind") == "DIALOGUE" else esc(beat["text"])


with st.sidebar:
    st.markdown("**Run it on new scripts**")
    st.caption("Upload one script file per episode, or a single .zip of them. A whole series in one file also works.")
    uploads = st.file_uploader("Episode scripts", type=["txt", "md", "fountain", "text", "zip"], accept_multiple_files=True, label_visibility="collapsed")
    use_sample = st.checkbox("Use the two-episode sample show instead", value=not uploads)
    choice = st.radio("Mode", list(MODES), format_func=lambda m: MODES[m][0], horizontal=True)
    st.caption(MODES[choice][1])
    passcode = ""
    if choice == "full":
        passcode = st.text_input("Passcode", type="password")
    model = st.text_input("Model", "nvidia/nvidia/nemotron-3-ultra-550b-a55b", disabled=choice == "offline")
    top = st.slider("How many promos", 5, 25, 15)
    if st.button("Find promos", type="primary", use_container_width=True):
        work = Path(tempfile.mkdtemp(prefix="promofinder-"))
        source = SAMPLE
        if uploads and not use_sample:
            unpack(uploads, work)
            source = work
        blocked = None
        if choice == "full" and (not secret("FULL_PASSCODE") or passcode != secret("FULL_PASSCODE")):
            blocked = "Full mode is locked on the public app. Use Fast here, or run Full from the command line."
        if choice == "fast" and source is not SAMPLE:
            from promofinder.doctor import check_input
            found = check_input(str(source))
            if found.get("episodes", 0) > MAX_PUBLIC_EPISODES:
                blocked = f"{found['episodes']} episodes is more than this public app runs at once ({MAX_PUBLIC_EPISODES}). Use the command line for bigger shows."
        if blocked:
            st.warning(blocked)
        else:
            lines = []
            with st.status("Reading scripts and picking promos", expanded=True) as status:
                def log(message: str):
                    lines.append(message)
                    if message.startswith("[") or message.startswith("WARNING") or message.startswith("Note"):
                        status.write(message)
                        if message.startswith("["):
                            status.update(label=message.split("] ", 1)[-1])
                try:
                    result = run(
                        str(source), out_root=str(OUTPUTS), mode="offline" if choice == "offline" else "llm",
                        model=model if choice != "offline" else None, top=top,
                        config_path=str(CONFIG), profile=None if choice == "offline" else choice, log=log,
                    )
                    degraded = result["meta"].get("degraded")
                    status.update(label=f"Done in {result['meta']['seconds']:.0f}s" + (" (some steps fell back to rules)" if degraded else ""), state="complete")
                    st.session_state["run_dir"] = str(Path(result["out_dir"]).resolve())
                    st.session_state.pop("list", None)
                    if not result["records"]:
                        st.warning("No promo fits the rules in these scripts. Check that times and speaker lines are in a supported format.")
                    else:
                        st.rerun()
                except SystemExit as exc:
                    status.update(label="Nothing to read", state="error")
                    st.error(str(exc) or "No screenplay episodes found in the upload.")
                except Exception as exc:
                    status.update(label="Run failed", state="error")
                    st.error(str(exc))
            if lines:
                with st.expander("Full log"):
                    st.code("\n".join(lines[-40:]), language=None)

runs = list_runs()
if not runs:
    st.info("No runs yet. Open the sidebar and run the sample show.")
    st.stop()

current = st.session_state.get("run_dir") or str(RAW / "final_run")
start = next((i for i, p in enumerate(runs) if str(p) == current), 0)

head_l, head_r = st.columns([3, 2])
with head_l:
    st.markdown(f'<div class="brand">{logo()}<span class="slash">/</span><span class="app">PromoFinder</span></div>', unsafe_allow_html=True)
with head_r:
    picked = st.selectbox("Run", runs, index=start, format_func=run_name, label_visibility="collapsed")
if str(picked) != current:
    st.session_state["run_dir"] = str(picked)
    st.session_state.pop("list", None)

payload = json.loads((picked / "promos.json").read_text(encoding="utf-8"))
meta, promos = payload["meta"], payload["promos"]
title = payload["show"].replace("-", " ").strip().title() if payload["show"].islower() else payload["show"]
how = "Nemotron 3 Ultra picks and judges, Mistral Large 4 double-checks" if meta["mode"] == "llm" else "rules only, no model"
st.markdown(
    f'<div class="bar"><div class="show"><b>{esc(title)}</b> &nbsp;·&nbsp; {meta["episodes"]} episodes &nbsp;·&nbsp; '
    f'{meta["candidates"]:,} possible clips scored &nbsp;·&nbsp; {len(promos)} promos &nbsp;·&nbsp; {how}</div></div>',
    unsafe_allow_html=True,
)

GUIDE = [
    ("Pick a promo on the left",
     "The list is already ranked. <b>Post first</b> (#1) is the safest strong clip to run first. <b>Test next</b> are the ones to try against it. "
     "<b>Retargeting</b> clips give away late twists, so they are for people already watching. Click a row to open it."),
    ("Read it on the right",
     "The exact cut, a bar showing where it sits in the episode (bright red is the first 3 seconds, where the hook must land), "
     "the hook and cliffhanger lines, why it works and why it has that rank, anything to check before posting, the full transcript "
     "with the hook and cliffhanger marked, and the scores from two AI judges."),
    ("Approve or reject",
     "At the bottom of each promo. Add a note if you like. Decisions are saved with the run so the ranking can be tuned later."),
    ("Run it on new scripts",
     "Use the panel on the left (the <b>&raquo;</b> arrow if it is closed). Upload one script file per episode (.txt, .md or .fountain), "
     "a .zip of them, or a whole series in one file, or use the two-episode sample. <b>Fast</b> uses the AI, about 3-5 minutes for 50 episodes. "
     "<b>Rules only</b> takes seconds and needs no key. <b>Full</b> adds the second judge (20-25 minutes) and needs a passcode here. "
     "Progress shows live. The new run then appears in the dropdown at the top right, next to the <b>Submitted run</b>."),
]
with st.expander("How to use this app", expanded=True):
    st.markdown(
        '<div class="guide">' + "".join(
            f'<div><div class="h"><span class="n">{i}</span>{h}</div><div class="b">{b}</div></div>' for i, (h, b) in enumerate(GUIDE, 1)
        ) + "</div>",
        unsafe_allow_html=True,
    )

ROLE = {"control": "Post first", "challenger": "Test next", "retargeting": "Retargeting"}
table = pd.DataFrame([{
    "#": p["rank"],
    "Clip": " + ".join(f"Ep {s['episode']}" for s in p["segments"]) + f"  {p['segments'][0]['start'][:5]}",
    "Length": f"{p['duration']:.0f}s",
    "Use": ROLE.get(p.get("role"), p.get("role", "")),
} for p in promos])

left, right = st.columns([1.25, 1.5], gap="large")
with left:
    st.markdown('<div class="label">Ranked promos</div>', unsafe_allow_html=True)
    event = st.dataframe(
        table, hide_index=True, on_select="rerun", selection_mode="single-row", key="list", height=35 * len(table) + 38,
        column_config={"#": st.column_config.NumberColumn(width=34), "Clip": st.column_config.TextColumn(width=150), "Length": st.column_config.TextColumn(width=58), "Use": st.column_config.TextColumn(width=118)},
    )
    st.caption("Click a row to open it. #1 is the safest early clip to post first. Retargeting cuts give away late twists, so they are for people already watching.")

rows = event.selection.rows if event and event.selection else []
p = promos[rows[0]] if rows else promos[0]
judge = p.get("judge") or {}
role = p.get("role", "challenger")

with right:
    segs = " + ".join(f"Ep {s['episode']}, {s['start']} to {s['end']}" for s in p["segments"])
    role_html = {"control": '<span class="first">Post first</span>', "retargeting": '<span class="retarget">Retargeting</span>'}.get(role, "Test next")
    st.markdown(
        f'<div class="label">Promo #{p["rank"]}</div><div class="title">{esc(segs)}</div>'
        f'<div class="meta">{role_html} &nbsp;·&nbsp; {p["duration"]:.1f} s &nbsp;·&nbsp; {esc(p["hook_type"])} &nbsp;·&nbsp; sends viewers to episode {p["resume_episode"]}</div>'
        f"{timeline(p)}",
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="label">Opens on</div><div class="quote">{said(p["hook"])}<span class="at">Ep {p["hook"]["episode"]}, {p["hook"]["time"]}</span></div>'
        f'<div class="label">Cuts on</div><div class="quote">{said(p["cliffhanger"])}<span class="at">Ep {p["cliffhanger"]["episode"]}, {p["cliffhanger"]["time"]}</span></div>'
        f'<div class="label">Why it works</div><div class="text">{esc(p["why_it_works"])}</div>'
        f'<div class="label">Why it is ranked here</div><div class="text">{esc(p.get("rank_reason", ""))}</div>',
        unsafe_allow_html=True,
    )
    checks = []
    risky = [f.split(":")[0].replace("_", " ") for f in p["policy_flags"] if not f.endswith(":low")]
    if risky:
        checks.append("Ad review: " + ", ".join(risky))
    if judge.get("unexplained_refs"):
        checks.append("A new viewer may not know: " + ", ".join(judge["unexplained_refs"]))
    if judge.get("craft"):
        checks.append("Craft: " + ", ".join(judge["craft"]))
    if checks:
        st.markdown('<div class="label">Check before posting</div>' + "".join(f'<div class="warn">{esc(c)}</div>' for c in checks), unsafe_allow_html=True)

    st.markdown('<div class="label">Transcript</div>' + transcript(p), unsafe_allow_html=True)

    parts = []
    if isinstance(judge.get("hook"), (int, float)):
        parts.append(f'Judge: hook <b>{judge["hook"]:g}</b>, cliffhanger <b>{judge["cliffhanger"]:g}</b>, makes sense alone <b>{judge["standalone"]:g}</b> (out of 5)')
    jury = judge.get("jury") or {}
    if "standalone" in jury:
        parts.append(f'Second judge: <b>{jury.get("hook", 0):g}</b>, <b>{jury.get("cliffhanger", 0):g}</b>, <b>{jury["standalone"]:g}</b>')
    if parts:
        st.markdown('<div class="label">Scores</div><div class="scores">' + "<br>".join(parts) + "</div>", unsafe_allow_html=True)

    st.markdown('<div class="label">Your call</div>', unsafe_allow_html=True)
    note = st.text_input("Note", key=f"note-{p['id']}", placeholder="Optional note for the editor", label_visibility="collapsed")
    a, r, _ = st.columns([1, 1, 2])
    for col, verdict in ((a, "approve"), (r, "reject")):
        if col.button(verdict.capitalize(), key=f"{verdict}-{p['id']}", type="primary" if verdict == "approve" else "secondary", use_container_width=True):
            with open(picked / "feedback.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"id": p["id"], "rank": p["rank"], "verdict": verdict, "note": note, "at": datetime.now().isoformat(timespec="seconds")}) + "\n")
            st.toast(f"Saved: {verdict} #{p['rank']}")

st.markdown(
    '<div class="foot">Prototype by Vatsal Kumar for the Kuku AI Generalist assignment, Problem 1. Not an official Kuku product. '
    'Code and raw outputs: <a href="https://github.com/vatsal3512/kuku-promo-finder">github.com/vatsal3512/kuku-promo-finder</a></div>',
    unsafe_allow_html=True,
)
