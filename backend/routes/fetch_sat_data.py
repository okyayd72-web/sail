"""
fetch_sat_data.py
-----------------
One-time data pull. Reads tennis_schools.json, queries the U.S. Dept. of
Education College Scorecard API, and writes ONE new field into each school
it can confidently match:
    "avg_sat_total"  — full composite SAT (Math + Critical Reading), from:
        1. latest.admissions.sat_scores.average.overall  (preferred)
        2. latest.admissions.sat_scores.midpoint.math
           + latest.admissions.sat_scores.midpoint.critical_reading  (fallback)

The existing "avg_sat" field (SAT Math subscore) is NEVER overwritten.
Schools without a usable Scorecard SAT value simply receive no new field.

HOW TO RUN (Windows PowerShell), from backend\\routes\\:
    1. Set your key for this session (paste your real key):
         $env:SCORECARD_API_KEY="your_key_here"
    2. Close tennis_schools.json in any editor that has it open.
    3. Run:
         cd backend\\routes
         python fetch_sat_data.py
"""

import difflib
import json
import os
import re
import shutil
import time
import urllib.parse
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(HERE, "tennis_schools.json")

API_BASE = "https://api.data.gov/ed/collegescorecard/v1/schools"
FIELDS = (
    "id,school.name,school.city,school.state,"
    "latest.admissions.sat_scores.average.overall,"
    "latest.admissions.sat_scores.midpoint.math,"
    "latest.admissions.sat_scores.midpoint.critical_reading"
)
PER_PAGE = 100

_PUNCT = re.compile(r"[.,'&\-()]")
_WS = re.compile(r"\s+")

_DISTINGUISHERS = {
    "tech", "technical", "community", "junior", "online",
    "downtown", "branch", "extension", "graduate", "seminary",
}


def normalize(name):
    if not name:
        return ""
    n = name.lower().strip()
    n = _PUNCT.sub(" ", n)
    n = n.replace(" the ", " ")
    if n.startswith("the "):
        n = n[4:]
    n = _WS.sub(" ", n).strip()
    for suffix in (" main campus", " online campus", " campus"):
        if n.endswith(suffix):
            n = n[: -len(suffix)].strip()
    return n


def fetch_state(state, api_key):
    results = []
    page = 0
    while True:
        params = {
            "api_key": api_key,
            "school.state": state,
            "fields": FIELDS,
            "per_page": PER_PAGE,
            "page": page,
        }
        url = API_BASE + "?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise SystemExit("ERROR: API key rejected (403). Check $env:SCORECARD_API_KEY.")
            if e.code == 429:
                print("  Rate limit hit (429). Waiting 60s...")
                time.sleep(60)
                continue
            raise SystemExit(f"ERROR: HTTP {e.code} for state {state}: {e}")
        except Exception as e:
            raise SystemExit(f"ERROR: network problem for state {state}: {e}")

        meta = data.get("metadata", {})
        batch = data.get("results", [])
        results.extend(batch)

        total = meta.get("total", 0)
        if (page + 1) * PER_PAGE >= total or not batch:
            break
        page += 1
        time.sleep(0.3)

    return results


def extract_sat(record):
    """Return composite SAT integer from a Scorecard record, or None."""
    overall = record.get("latest.admissions.sat_scores.average.overall")
    if overall is not None:
        try:
            return int(round(float(overall)))
        except (ValueError, TypeError):
            pass

    math = record.get("latest.admissions.sat_scores.midpoint.math")
    reading = record.get("latest.admissions.sat_scores.midpoint.critical_reading")
    if math is not None and reading is not None:
        try:
            return int(round(float(math) + float(reading)))
        except (ValueError, TypeError):
            pass

    return None


def main():
    api_key = os.getenv("SCORECARD_API_KEY", "").strip()
    if not api_key:
        print("ERROR: No API key found.")
        print('Set it first in PowerShell:  $env:SCORECARD_API_KEY="your_key_here"')
        return

    if not os.path.exists(JSON_PATH):
        print(f"ERROR: tennis_schools.json not found at {JSON_PATH}")
        return

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        schools = json.load(f)

    states = sorted({(s.get("state") or "").strip() for s in schools if s.get("state")})
    print(f"Found {len(schools)} schools across {len(states)} states. Querying Scorecard...\n")

    # Build per-state index
    index = {}
    names_by_state = {}

    for i, state in enumerate(states, 1):
        records = fetch_state(state, api_key)
        idx = {}
        names = []
        for r in records:
            raw_name = r.get("school.name")
            if not raw_name:
                continue
            nn = normalize(raw_name)
            idx[nn] = r
            names.append((nn, raw_name))
        index[state] = idx
        names_by_state[state] = names
        print(f"  [{i}/{len(states)}] {state}: {len(records)} institutions")

    # Match and write avg_sat_total
    matched = 0
    sat_written = 0

    for s in schools:
        name = s.get("school")
        state = (s.get("state") or "").strip()
        if not name or not state:
            continue
        nn = normalize(name)
        rec = index.get(state, {}).get(nn)

        if rec is None:
            # Try fuzzy match
            norms = [norm for (norm, _orig) in names_by_state.get(state, [])]
            close = difflib.get_close_matches(nn, norms, n=1, cutoff=0.88)
            if close:
                own_tokens = set(nn.split())
                sugg_tokens = set(close[0].split())
                added = sugg_tokens - own_tokens
                if added & _DISTINGUISHERS:
                    close = []
            if close:
                rec = index[state][close[0]]

        if rec is not None:
            matched += 1
            sat = extract_sat(rec)
            if sat is not None:
                s["avg_sat_total"] = sat
                sat_written += 1

    # Back up and write
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(HERE, f"tennis_schools.backup-{stamp}.json")
    shutil.copy2(JSON_PATH, backup)
    print(f"\nBackup saved: {os.path.basename(backup)}")

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(schools, f, ensure_ascii=False, indent=2)

    print("=" * 50)
    print(f"Schools matched in Scorecard: {matched}")
    print(f"avg_sat_total written:        {sat_written}")
    print(f"Schools with no SAT data:     {len(schools) - sat_written} (gracefully skipped)")
    print("=" * 50)


if __name__ == "__main__":
    main()
