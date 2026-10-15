# DepExit

### Verified dependency migrations, powered by Gemma 4

**Team Travis Tanner** · Track 1 — *Gemma 4: Dependency Resilience*

DepExit is an open-source developer tool that finds at-risk dependencies in a Python repository, uses **Gemma 4** to plan their replacement, **actually applies and tests each replacement** in an isolated environment, repairs failed attempts in a self-healing loop, and packages all of the evidence into a reusable **Dependency Exit Capsule**.

> **The core rule: the AI never states facts.**
> Plain code observes the repository and executes the tests. Gemma 4 reasons about that evidence. Every line of the capsule is labelled with where it came from, so AI suggestions are never mixed with verified results.

---

## Results on the target repository (`rishrek/LinkWatch`)

Full run on Python 3.12 with Gemma 4 (`gemma4:e4b`) running locally:

| Measure | Result |
|---|---|
| Dependencies analysed | **15** |
| High-risk dependencies found | **6** (plus 4 medium, 4 low) |
| Dependencies given an AI migration plan | **14** |
| **AI migrations proven by running tests** | **10 of 14** |
| LinkWatch's own test suite — before → after | **9 / 10 → 10 / 10** |
| AI-written equivalence tests (each first confirmed on the original code) | **21 / 21 pass** |
| Existing tests broken by the migrations | **0** |

**Verified migrations:** `nose`, `jinja2`, `appdirs → platformdirs`, `setuptools`, `idna`, `chardet`, `six`, `rich`, `python-dateutil`, `pytest`

**Not verified — reported honestly with the exact errors in the capsule:** `certifi`, `pydantic`, `requests`, `toml`

### Problems DepExit found on its own

These were detected by reading the code and running it, not by any hard-coded knowledge of LinkWatch:

- **`pydantic` — impossible manifest conflict.** `requirements.txt` pins `==1.10.13` while `pyproject.toml` requires `>=2`. No released version satisfies both, and the two install paths resolve to different major versions.
- **`requests` — private API and monkey-patching.** `linkwatch/encoding.py` imports the private `requests.utils._parse_content_type_header`, and `linkwatch/http_patch.py` overwrites `requests.Session.request` at runtime.
- **`certifi` — undeclared dependency.** Imported in `linkwatch/checker.py` but declared nowhere; it only works because `requests` happens to install it.
- **`jinja2` — broken on Python 3.12.** `import jinja2` fails (`cannot import name 'soft_unicode' from 'markupsafe'`), which is the cause of the one failing test.
- **`nose` — cannot run on Python 3.12.** Unreleased since 2015; importing it fails (`No module named 'imp'`).
- **`pkg_resources` / `setuptools`** — deprecated API kept alive by a pinned `setuptools`.
- Declared-but-unused packages (`six`, `idna`), unpinned packages, and a commented-out requirement.

The full results are in [`capsule/report.html`](capsule/report.html) (visual report), [`capsule/capsule.json`](capsule/capsule.json) (machine-readable) and [`capsule/capsule.md`](capsule/capsule.md).

---

## How it works

```
  repository
      │
      ▼
 1. SCAN          OBSERVED   Parse requirements*.txt / pyproject.toml / setup.cfg.
                             Walk the Python syntax tree: imports, calls, private-API use, monkey-patches.
      │
 2. BASELINE      VERIFIED   Fresh Python 3.12 environment, import probes, full test run.
                             A second run when two manifests disagree.
      │
 3. RISK          OBSERVED   Live PyPI metadata (release age, versions behind, Python support,
                             yanked versions), GitHub archive status, conflicts, undeclared deps,
                             failures traced to the library where they originate.
                             Every indicator gets an id, e.g. jinja2:import_fails:2
      │
 4. TRIAGE        AI         Gemma 4 decides risk, action (replace / upgrade / remove / declare / pin /
                             keep), replacement and migration steps — citing indicator ids.
                 OBSERVED   Fact-check: invented evidence ids are flagged; every proposed
                             replacement is looked up on PyPI / the standard library.
      │
 5. MIGRATE       AI         Gemma 4 writes exact file edits + a behavioural-equivalence test.
                 VERIFIED   The equivalence test is run on the ORIGINAL code first (an invalid
                             AI test is discarded, never trusted). Edits are applied in a sandbox
                             and the project's own test suite is run on the REPLACEMENT.
                 AI ⇄       On failure, the real error output goes back to Gemma 4 for a repair.
      │
 6. COMBINE       VERIFIED   All verified migrations applied together; full suite re-run.
      │
 7. CAPSULE                  capsule.json · capsule.md · report.html · patches/ · tests/ · replay.sh
```

### Provenance labels

| Label | Meaning |
|---|---|
| **OBSERVED** | Read from repository files, the Python syntax tree, PyPI or GitHub. Deterministic, no AI. |
| **VERIFIED** | Produced by installing dependencies in an isolated environment and actually running code and tests. |
| **AI-GENERATED** | Produced by Gemma 4. A recommendation or hypothesis — not a fact until a VERIFIED section confirms it. |

---

## AI model disclosure

| | |
|---|---|
| **Model** | Gemma 4 — **`gemma4:e4b`** (instruction-tuned, ~4B effective parameters, open weights) |
| **Version** | Ollama library tag `gemma4:e4b`; the exact model id is recorded in every capsule and in `ai_transcript.jsonl` |
| **Access method** | **Local open weights via [Ollama](https://ollama.com)** (v0.40.4), native API at `http://localhost:11434/api/chat`, run on a 16 GB MacBook Air |
| **Terms** | [Gemma Terms of Use](https://ai.google.dev/gemma/terms) · [Gemma Prohibited Use Policy](https://ai.google.dev/gemma/prohibited_use_policy) |
| **Role in the tool** | Risk triage, replacement selection, migration planning, code edits, equivalence-test writing, and repairing failed migrations |

### Why we run Gemma 4 locally

DepExit was built to use Gemma 4 through a **hosted API** first. During the hackathon both hosted routes failed for reasons outside our code, so we added local inference as a third, fully supported provider. All three remain in the tool and can be switched with one line in `.env`.

**1. Google AI Studio (Gemini API) — rejected the API key.**
Every key AI Studio generated for our account had the new `AQ.` prefix, and every request was rejected, with both the `x-goog-api-key` header and the `?key=` parameter, for both `gemma-4-26b-a4b-it` and `gemma-4-31b-it`:

```json
{
  "error": {
    "code": 401,
    "message": "Request had invalid authentication credentials. Expected OAuth 2 access token, login cookie or other valid authentication credential. See https://developers.google.com/identity/sign-in/web/devconsole-project.",
    "status": "UNAUTHENTICATED",
    "details": [
      {
        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
        "reason": "ACCESS_TOKEN_TYPE_UNSUPPORTED",
        "metadata": { "service": "generativelanguage.googleapis.com" }
      }
    ]
  }
}
```

This matches an open issue reported by many developers on the [Google AI Developers Forum](https://discuss.ai.google.dev/t/aq-key-returns-401-access-token-type-unsupported-on-generatecontent/179102) with no confirmed fix.

**2. OpenRouter (hosted Gemma 4) — paid tier unavailable, free tier jammed.**
The paid model (`google/gemma-4-26b-a4b-it`) required purchased credits:

```json
{"error":{"message":"Insufficient credits. This account never purchased credits. Make sure your key is on the correct account or org, and if so, purchase more at https://openrouter.ai/settings/credits","code":402}}
```

Both free models (`google/gemma-4-26b-a4b-it:free` and `google/gemma-4-31b-it:free`) were overloaded at their upstream provider. DepExit automatically switched between the two and retried with back-off, but they stayed blocked for most of the event:

```json
{"error":{"message":"Provider returned error","code":429,"metadata":{"raw":"google/gemma-4-31b-it:free is temporarily rate-limited upstream. Please retry shortly, or add your own key to accumulate your rate limits","provider_name":"Google AI Studio"}}}
```

**3. Ollama (local open weights) — used for all results above.**
Running Gemma 4 locally removed every external dependency: no keys, no quotas, no rate limits, and the target code never leaves the machine. It also fits the spirit of the challenge — an open-source tool built on open weights. Two adaptations made the small local model reliable:

- **Larger context window.** Ollama's default context is too small for prompts that contain source files, so DepExit requests a 16K window (`OLLAMA_NUM_CTX`).
- **JSON robustness.** This engine has no structured-output mode (`HTTP 501: structured output is unavailable`), so DepExit detects that and falls back to parsing and repairing JSON from free text.

### Switching provider

```bash
# Local Gemma 4 (used for our results)
GEMMA_PROVIDER=ollama
GEMMA_MODEL=gemma4:e4b

# Google AI Studio / Gemini API
GEMMA_PROVIDER=gemini
GEMINI_API_KEY=...
GEMMA_MODEL=gemma-4-26b-a4b-it,gemma-4-31b-it

# OpenRouter (comma-separated models = automatic fallback)
GEMMA_PROVIDER=openrouter
OPENROUTER_API_KEY=...
GEMMA_MODEL=google/gemma-4-26b-a4b-it
```

---

## Quick start

**Requirements:** macOS or Linux, Python 3.12 or 3.13, [`uv`](https://docs.astral.sh/uv/), git, and [Ollama](https://ollama.com) for local Gemma 4 (16 GB RAM recommended).

```bash
# 1. Install
git clone <this repository> && cd depexit
uv venv -p 3.12 .venv && source .venv/bin/activate
uv pip install -r requirements.txt

# 2. Local Gemma 4
brew install ollama && brew services start ollama
ollama pull gemma4:e4b
printf 'GEMMA_PROVIDER=ollama\nGEMMA_MODEL=gemma4:e4b\n' > .env
python check_gemma.py                     # should print SUCCESS

# 3. Run on the target repository
python -m depexit https://github.com/rishrek/LinkWatch --workers 1 --max-fix 1 --out capsule
open capsule/report.html
```

| Flag | Purpose |
|---|---|
| `--only jinja2,appdirs` | Analyse and migrate only these dependencies (fast demo, ~5 min) |
| `--max-fix N` | AI repair attempts per dependency |
| `--workers N` | Dependencies migrated in parallel (use 1 for a local model) |
| `--no-ai` | Observed and verified evidence only, no Gemma — runs in ~30 s on any repository |
| `--no-migrate` | Analysis and recommendations only, skip executing replacements |
| `--ai-cache` | Save Gemma answers and reuse them on re-runs (development only; flagged in the capsule) |
| `--python 3.13` | Target interpreter (default 3.12) |

Rebuild the HTML report from an existing capsule without re-running anything:

```bash
python -m depexit.rerender capsule
```

Nothing is specific to LinkWatch — point DepExit at any Python repository with a pytest suite.

---

## The Dependency Exit Capsule

Each run writes a self-contained folder:

| File | Contents |
|---|---|
| `report.html` | Presentation-ready visual report: summary, charts, key findings, full evidence appendix. Works offline. |
| `capsule.json` | Machine-readable capsule (schema `dependency-exit-capsule/1.0`) — every field tagged with its provenance |
| `capsule.md` | The same content as readable Markdown |
| `patches/<dep>.patch`, `patches/combined.patch` | Verified migrations as `git apply`-able diffs |
| `tests/test_depexit_<dep>.py` | AI-written behavioural-equivalence tests, already run on both the original and the replacement |
| `ai_transcript.jsonl` | Every Gemma 4 call: purpose, model, latency, prompt hash, raw response |
| `replay.sh` | Re-runs original vs replacement on any machine to reproduce the evidence |

For every dependency the capsule records:
- dependency details
- risk indicators
- usage locations
- proposed replacement
- migration steps
- suggested tests
- executed test results for every attempt
- observed compatibility gaps, kept separate from the gaps the AI expected
- the fact-check of the AI's answer
- open concerns and limitations

---

## Design decisions

- **Facts and AI are kept apart.** Deterministic code gathers evidence; Gemma 4 only interprets it. The report never presents an AI claim as a result.
- **The AI is fact-checked.** Gemma 4 must cite the ids of real indicators. Invented ids are flagged as ungrounded, and every proposed package is checked on PyPI.
- **AI-written tests are not trusted blindly.** An equivalence test must first pass on the original code. If it doesn't, it is discarded, and the verdict relies only on the project's own tests.
- **A broken AI test cannot hide a working fix, or vice versa.** The project's test suite and the AI's tests are run separately.
- **No stale evidence.** Every run uses fresh sandboxes, and old test results are deleted before each run, so a crash can never be mistaken for a pass.
- **Failures are blamed precisely.** A failing test is attributed to the library where the error originates, not to every library its traceback passes through.

## Limitations

- Verification is only as strong as the project's test suite plus the validated equivalence tests. Untested code paths are listed as open concerns.
- `gemma4:e4b` is a small model. It handles version upgrades and package swaps well. Deeper rewrites, such as Pydantic v1 → v2 validators or replacing `requests` internals, were attempted but not verified in this run. A larger Gemma 4 model through the hosted API should do better.
- Python repositories with pytest only.
- Registry signals (release age, inactivity) are indicators, not proof that a package is unsafe.
- Security vulnerabilities are out of scope, as stated in the problem statement.

## Project structure

```
depexit/
  cli.py          orchestration of the pipeline
  scanner.py      manifest parsing + Python AST usage analysis        (OBSERVED)
  pypi.py         live PyPI / GitHub metadata                         (OBSERVED)
  risk.py         risk indicators with ids                            (OBSERVED)
  executor.py     sandboxed environments, import probes, pytest runs  (VERIFIED)
  gemma.py        Gemma 4 client: Ollama, Gemini API, OpenRouter
  analysis.py     AI triage + fact-check of AI claims
  migrate.py      AI edits, equivalence tests, self-repair loop
  capsule.py      capsule.json / capsule.md / patches / replay.sh
  report_html.py  visual HTML report
  rerender.py     rebuild the report from an existing capsule
check_gemma.py    one-command check that Gemma 4 is reachable
```

## Licence

MIT — see [LICENSE](LICENSE). Gemma 4 weights are used under the [Gemma Terms of Use](https://ai.google.dev/gemma/terms).

---

*Built by Team Travis Tanner.*
