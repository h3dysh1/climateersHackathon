"""Classify every building tile with the Claude API → frontend/public/data/roof_labels.json.

Results are cached: re-running only classifies buildings not yet labelled, so you never
pay or wait twice. Runs in MOCK mode without ANTHROPIC_API_KEY.

Usage (from backend/):
  python batch_classify.py            # all unlabelled buildings with a tile
  python batch_classify.py --limit 5  # quick test first
"""
import argparse
import base64
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))
from app import claude_client  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "frontend" / "public" / "data"
TILES = ROOT / "frontend" / "public" / "tiles"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--sleep", type=float, default=0.2, help="pause between calls (rate limits)")
    args = ap.parse_args()

    fc = json.loads((DATA / "buildings.geojson").read_text())
    out_path = DATA / "roof_labels.json"
    labels = json.loads(out_path.read_text()) if out_path.exists() else {}
    # Drop mock labels so real ones replace them.
    labels = {k: v for k, v in labels.items() if not v.get("mock")} if not claude_client.is_mock() else labels

    todo = [f["properties"]["id"] for f in fc["features"]
            if f["properties"]["id"] not in labels and (TILES / f"{f['properties']['id']}.png").exists()]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(todo)} to classify ({'MOCK' if claude_client.is_mock() else claude_client._model()})")

    for i, bid in enumerate(todo, 1):
        b64 = base64.b64encode((TILES / f"{bid}.png").read_bytes()).decode()
        labels[bid] = claude_client.classify_roof(b64, "image/png", bid)
        if i % 10 == 0 or i == len(todo):
            out_path.write_text(json.dumps(labels, indent=1))  # save progress as we go
            print(f"  {i}/{len(todo)}")
        time.sleep(args.sleep)
    out_path.write_text(json.dumps(labels, indent=1))
    print(f"saved {out_path}")


if __name__ == "__main__":
    main()
