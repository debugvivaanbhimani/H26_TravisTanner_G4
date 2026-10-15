# Team plan — 5 hours, 3 people

The core tool already works end-to-end (scan → baseline → risk → Gemma → migrate → fix loop →
combine → capsule). Your job now is to **run it with real Gemma, harden it, and make it shine**.
Do not rewrite it. Every change must keep `python -m depexit <LinkWatch> --out capsule` working.

## Hour 0 (everyone, 20 min)

```bash
pip install uv
pip install -r requirements.txt
cp .env.example .env        # paste the key — NEVER commit .env
python check_gemma.py       # must print the Gemma 4 model list and {"ok": true ...}
python -m depexit https://github.com/rishrek/LinkWatch --out capsule
```

If `check_gemma.py` lists a different Gemma 4 model name, put it in `.env` as `GEMMA_MODEL=`.
Open `capsule/report.html`. That is your starting point. Push to your public GitHub repo now.

## Rushin — lead, quality of AI output, pitch

1. Read the first real capsule end to end. For every dependency ask: is the AI's replacement
   sensible? Did it handle the subtle ones (pydantic manifest conflict, requests private API +
   monkey-patch, undeclared certifi, pkg_resources/setuptools, nose)? If not, improve the prompts
   in `depexit/analysis.py` (TRIAGE_PROMPT) and `depexit/migrate.py` (EDIT_PROMPT).
2. Own the README "AI model disclosure" table — confirm the exact model id from `check_gemma.py`.
3. Write the 3-minute pitch (below) and rehearse it twice.

Antigravity prompt:
> Read README.md and depexit/analysis.py. After running the tool on LinkWatch, the Gemma triage
> for <dependency> was <paste>. Improve TRIAGE_PROMPT so Gemma <what you want>, without
> hard-coding any package names or LinkWatch-specific answers. Keep the JSON schema identical.

## Teammate 2 — engine reliability (depexit/migrate.py, executor.py)

Goal: as many dependencies as possible end with status `verified`, honestly.
1. Run the full tool. For each `unresolved` dependency read the attempts in capsule.json and fix
   the *tool* (prompt clarity, which files are sent to Gemma, error text fed back) — never the
   target repo by hand.
2. Stretch: when an edit's `search` text is not found, send Gemma the exact failure and retry
   instead of losing the edit.
3. Make sure Ctrl-C mid-run still leaves a partial capsule (wrap the migration loop).

Antigravity prompt:
> In depexit/migrate.py the dependency <name> ends "unresolved". Here is its attempts array from
> capsule.json: <paste>. Improve the fix loop so the real error reaches Gemma more clearly. Do not
> special-case any package; do not weaken the verification rules in executor.compare_runs.

## Teammate 3 — report + generality proof

1. Polish `depexit/report_html.py`: add an "Evidence chain" diagram per dependency
   (indicator → AI claim → test result), and a printable view. Keep it a single offline file.
2. Generality proof (very important for judges): find a small public Python repo with
   pytest + a requirements.txt and run the tool on it. Fix anything that breaks. Mention it in
   the README and show it in the demo.
3. Record a 2-minute screen video of a full run + report as a backup in case the demo Wi-Fi or
   API dies.

Antigravity prompt:
> depexit/report_html.py renders capsule.json into a self-contained page. Add <feature>. Keep the
> OBSERVED / VERIFIED / AI-GENERATED colour coding on every section, no external assets.

## Rules

- **15:15 code freeze.** After that only README, pitch and video.
- Never commit `.env`. Never hard-code LinkWatch answers (the brief penalises pre-written output).
- Commit after every working change so you can roll back.
- Run the full LinkWatch analysis once before the demo and keep that capsule; demo live with
  `--only jinja2,appdirs` so it finishes in ~2 minutes.

## 3-minute pitch skeleton

1. **Problem (20s):** dependency rot is found only when things break; AI advice alone is unverifiable.
2. **Idea (20s):** code observes, Gemma reasons, execution verifies — every fact is labelled.
3. **Live run (60s):** `--only jinja2,appdirs`; show baseline 9/1 → migration → repair loop → green.
4. **Report (50s):** subtle catches (manifest conflict nobody can satisfy, private `requests` API,
   monkey-patch, undeclared certifi); the grounding check that catches AI inventing evidence;
   the combined run.
5. **Reusable (20s):** capsule.json, patches, equivalence tests, replay.sh; second repo proof.
6. **Honesty (10s):** open concerns section — what we could not verify.
