# kuku-promo-finder

Finds promo clips (20-60 s) in microdrama screenplays and ranks them.

Live app: https://kuku-promo-finder.streamlit.app

You give it a folder of episode scripts. It gives back a list of promos, each with the episode, start and end time of every segment, the hook, the cliffhanger, a line on why it works and why it got its rank.

The LLM never writes timestamps itself. It only points at lines in the script, and the code works out the cut points (on shot changes, never in the middle of a line). I tried letting the model write timestamps directly: 23 out of 100 promos came out broken.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
```

Put your NVIDIA NIM key in `.env` (free at build.nvidia.com). More keys can go in as `NVIDIA_API_KEY2`, `NVIDIA_API_KEY3`; the tool rotates between them when one gets rate limited.

## Run

```bash
python -m promofinder check --input path/to/scripts
python -m promofinder run --input path/to/scripts
python -m promofinder run --offline --input tests/fixtures/sample_show
streamlit run app.py
```

- `check` shows how the scripts were parsed, before spending any API calls
- `run` is the full pipeline, about 20-25 min for 50 episodes on the free tier
- `--offline` uses only rules, no API key needed, takes a few seconds
- `app.py` opens a small review app where you can go through the promos and approve or reject them

Results go to `outputs/<show>/<time>-<mode>/`:

| File | What's in it |
|---|---|
| `promos.md` | the ranked list, easy to read |
| `promos.json` / `promos.csv` | same list with all fields (scores, ad flags, spoiler level, which episode it sends viewers to) |
| `edl.csv` | edit list: promo, segment, episode, in, out |
| `ffmpeg_cuts.sh` | cuts the promos from the episode videos once you have them |
| `candidates_scored.jsonl` | every clip that was scored |

## Changing the model

The model is just a `provider/model` string:

```bash
python -m promofinder run --input scripts --model groq/llama-3.3-70b-versatile
python -m promofinder run --input scripts --model gemini/gemini-2.5-flash
python -m promofinder run --input scripts --jury-model none
```

Supported: `nvidia`, `groq`, `gemini`, `openrouter`, `openai`, `together`, `mistral`, `deepseek`, `ollama`, and `custom` for any OpenAI-compatible endpoint (set `PROMO_LLM_BASE_URL` and `PROMO_LLM_API_KEY`). Default is Nemotron 3 Ultra for picking and judging, with Mistral Large 4 as a second judge. Weights and limits are in `config.yaml`.

## How it works

1. Parse the scripts into scenes, timed lines, speakers and camera shots.
2. Score every line as a possible hook or cliffhanger (rules), and ask the LLM for the best hook and cliffhanger in each episode.
3. Build about 3,000 possible clips: single stretches, clips across an episode break, and two-part montages. Drop anything that's not 20-60 s, has the hook later than 3 s, or ends more than 1.5 s after the cliffhanger.
4. A "cold viewer" LLM judges the best ~140 clips twice. It sees only the clip, never the show. A clip that scores under 3/5 on making sense alone is dropped.
5. A second model from a different family checks the shortlist and can veto clips.
6. Code-side checks the judges miss: no spoken line in the first 3 s, a one-word opening, a long silent end, length over 50 s.
7. Pick a varied list (one promo per scene), order it with pairwise comparisons, and put the safest early-episode clip at #1 as the one to post first. Big spoilers go to the end, for retargeting.

## Checking quality

```bash
python -m promofinder eval --run outputs/<show>/<run> --input path/to/scripts
python -m promofinder compare outputs/<show>/<run_a> outputs/<show>/<run_b>
python -m promofinder baseline --input path/to/scripts --out outputs/baseline.json
python -m promofinder audit outputs/<show>/<run_a> outputs/<show>/<run_b> --input path/to/scripts --model nvidia/minimaxai/minimax-m3.1-flash --batch 3 --concurrency 9
python -m promofinder agree --run outputs/<show>/<run> --human eval/human_scores.csv
```

- `eval` checks every promo is valid (length, hook position, no split lines, text matches the script)
- `compare` shows how much two runs agree on the top 10
- `baseline` asks the model for timestamps directly, then runs the same checks on them
- `audit` has a model that wasn't used in the run judge the top promos of several runs blind, so a change isn't graded only by the model that made it
- `agree` compares the judge's scores with your own

## Tests

```bash
python -m pytest -q
```

The tests use a small made-up show in `tests/fixtures/sample_show` and a fake model, so they don't need a key or network.

## Script format

Plain text, one file per episode, with blocks like:

```
**CHARACTER NAME (Delivery, Tags):**
Start: (00:11.30) | End: (00:13.10)
"Line of dialogue."
```

`CAMERA`, `ACTION` and `SOUND FX` blocks use the same timing line. It also reads `[mm:ss - mm:ss]` and SRT-style `hh:mm:ss,mmm --> hh:mm:ss,mmm` ranges, tags without bold, and `.md` / `.fountain` files. Run `check` first on a new show to see if anything looks off.

Outputs from the full input pack are in `raw_outputs/`. The show scripts themselves are not in this repo.
