"""Run this first: confirms your key works and shows which Gemma 4 models you can use."""
import os, sys
import requests
sys.path.insert(0, os.path.dirname(__file__))
from depexit.util import load_dotenv
load_dotenv()
key = os.environ.get("GEMINI_API_KEY")
if not key:
    sys.exit("GEMINI_API_KEY missing — copy .env.example to .env and paste your key.")
r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", params={"key": key, "pageSize": 200}, timeout=30)
r.raise_for_status()
gemma = [m["name"].split("/")[-1] for m in r.json().get("models", []) if "gemma-4" in m["name"]]
print("Gemma 4 models available to your key:", gemma or "NONE FOUND")
from depexit.gemma import Gemma
g = Gemma()
print(f"Calling {g.model} ...")
print(g.generate_json('Return {"ok": true, "model_says": "<one short sentence>"}', "smoke-test"))
