"""Run this first: confirms your Gemma 4 access works (Gemini API, OpenRouter or local Ollama)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from depexit.util import load_dotenv

load_dotenv()
from depexit.gemma import Gemma, GemmaError

try:
    g = Gemma()
except GemmaError as exc:
    sys.exit(f"Setup problem: {exc}")
print(f"Provider: {g.label}\nModel(s): {', '.join(g.models)}\nCalling Gemma (first call can take up to a minute) ...")
try:
    print(g.generate_json('Return {"ok": true, "model_says": "<one short sentence>"}', "smoke-test", retries=6))
    print("\nSUCCESS - Gemma 4 is reachable. Now run the tool.")
except GemmaError as exc:
    sys.exit(f"\nFAILED: {exc}")
