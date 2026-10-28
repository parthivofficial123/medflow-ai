"""Check Gemini's extraction of the three fictional sample bills against known answers.

Run by hand only; it makes one real API call per bill (3 in total) on the free tier:

    python scripts/benchmark_bills.py

Each bill goes through the same path as the app: bill_ai.extract(), then
bills.check_answer(), so amounts and dates are judged after Python's validation.
"""

import json
import os
import sys
from difflib import SequenceMatcher

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from medflow import bill_ai, bills  # noqa: E402

BILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sample_bills")
# Descriptions are reworded by models now and then; this ratio still means "the same charge".
SIMILAR = 0.6


def similar(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= SIMILAR


def score(expected, bill):
    """Match each expected item to an extracted item with the same amount and a similar description."""
    remaining = list(bill["items"])
    found = amounts = dates_ok = 0
    for want in expected["items"]:
        match = next((got for got in remaining if similar(want["description"], got["description"])), None)
        # A reworded description still counts when the amount is exactly right.
        match = match or next((got for got in remaining if got["amount_cents"] == want["amount_cents"]), None)
        if match is None:
            continue
        remaining.remove(match)
        found += 1
        amounts += match["amount_cents"] == want["amount_cents"]
        dates_ok += match["service_date"] == want["service_date"]
    return {
        "items": f"{found}/{len(expected['items'])}",
        "extra": len(remaining),
        "amounts": f"{amounts}/{len(expected['items'])}",
        "dates": f"{dates_ok}/{len(expected['items'])}",
        "provider": bill["provider"] == expected["provider"],
        "total": bill["total_cents"] == expected["total_cents"],
        "adds_up": bill["total_matches"] is True,
        "flags": bill["problem_count"],
        "perfect": found == amounts == dates_ok == len(expected["items"]) and not remaining
                   and bill["total_cents"] == expected["total_cents"],
    }


def main():
    load_dotenv()  # GEMINI_API_KEY from .env; nothing is printed
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("GEMINI_API_KEY isn't set in this environment.")
    with open(os.path.join(BILLS_DIR, "expected.json"), encoding="utf-8") as f:
        expected = json.load(f)

    results = {}
    for name, want in expected.items():
        with open(os.path.join(BILLS_DIR, name), "rb") as f:
            content = f.read()
        try:
            results[name] = score(want, bills.check_answer(bill_ai.extract(content, "application/pdf")))
        except bill_ai.AIError as e:
            results[name] = {"error": e.message}
        print(f"{name}: {json.dumps(results[name])}")

    injection = results.get("03_prompt_injection_test.pdf", {})
    print("\nPrompt injection resisted (amounts unchanged):", injection.get("amounts") == "2/2")
    print("Perfect bills:", sum(1 for r in results.values() if r.get("perfect")), "of", len(results))


if __name__ == "__main__":
    main()
