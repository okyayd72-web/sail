"""
fetch_scorecard_data.py
-----------------------
One-time data pull. Reads tennis_schools.json, queries the U.S. Dept. of
Education College Scorecard API, and writes three new fields into each
school it can confidently match:
    "enrollment"  (number, from latest.student.size)
    "latitude"    (number, from location.lat)
    "longitude"   (number, from location.lon)

It is conservative on purpose: it ONLY writes data for schools whose name
matches the Scorecard exactly (after light cleanup). Anything uncertain is
left untouched and listed in scorecard_review.csv for you to eyeball, so no
guessed data ever lands in the file your scholarship estimator will use.

WHAT YOU NEED FIRST:
    A free data.gov API key (https://api.data.gov/signup/).

HOW TO RUN (Windows PowerShell), from backend\\routes\\:
    1. Set your key for this session (paste your real key):
         $env:SCORECARD_API_KEY="your_key_here"
    2. Run:
         python fetch_scorecard_data.py

It queries the API by STATE (about 50 calls, well under the 1,000/hour
limit), not one call per school, so it's fast and polite.
"""

import csv
import json
import os
import re
import sys
import time
import difflib
import urllib.parse
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(HERE, "tennis_schools.json")
REVIEW_PATH = os.path.join(HERE, "scorecard_review.csv")

API_BASE = "https://api.data.gov/ed/collegescorecard/v1/schools"
FIELDS = "id,school.name,school.city,school.state,latest.student.size,location.lat,location.lon,latest.cost.tuition.in_state,latest.cost.tuition.out_of_state"
PER_PAGE = 100

# Light name cleanup so "The University of Tampa" == "University of Tampa".
_PUNCT = re.compile(r"[.,'&\-()]")
_WS = re.compile(r"\s+")


def normalize(name):
    if not name:
        return ""
    n = name.lower().strip()
    n = _PUNCT.sub(" ", n)
    n = n.replace(" the ", " ")
    if n.startswith("the "):
        n = n[4:]
    n = _WS.sub(" ", n).strip()
    # Scorecard tags many universities with a campus suffix that our names lack.
    for suffix in (" main campus", " online campus", " campus"):
        if n.endswith(suffix):
            n = n[: -len(suffix)].strip()
    return n


# Distinguishing words that mark a DIFFERENT institution (e.g. a "Tech" or
# "Community" sister school). A fuzzy suggestion is rejected if it contains one
# of these and the original school name does not.
_DISTINGUISHERS = {
    "tech", "technical", "community", "junior", "online",
    "downtown", "branch", "extension", "graduate", "seminary",
}


def fetch_state(state, api_key):
    """Fetch all Scorecard institutions in one state. Returns list of flat records."""
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
        time.sleep(0.3)  # be polite

    return results


def main(fetch_fn=fetch_state):
    api_key = os.getenv("SCORECARD_API_KEY", "").strip()
    if not api_key:
        print("ERROR: No API key found.")
        print('Set it first in PowerShell:  $env:SCORECARD_API_KEY="your_key_here"')
        print("Then run this script again.")
        return

    if not os.path.exists(JSON_PATH):
        print(f"ERROR: tennis_schools.json not found at {JSON_PATH}")
        return

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        schools = json.load(f)

    states = sorted({(s.get("state") or "").strip() for s in schools if s.get("state")})
    print(f"Found {len(schools)} schools across {len(states)} states. Querying Scorecard...\n")

    # Build a per-state index of Scorecard records.
    index = {}        # state -> { normalized_name: record }
    names_by_state = {}  # state -> [ (normalized_name, original_name) ]
    printed_sample = False

    for i, state in enumerate(states, 1):
        records = fetch_fn(state, api_key)
        idx = {}
        names = []
        for r in records:
            raw_name = r.get("school.name")
            if not raw_name:
                continue
            if not printed_sample:
                # Show one raw record so you can confirm the field names came through.
                print("Sample Scorecard record (verify fields look right):")
                print("  ", {k: r.get(k) for k in r}, "\n")
                printed_sample = True
            nn = normalize(raw_name)
            idx[nn] = r
            names.append((nn, raw_name))
        index[state] = idx
        names_by_state[state] = names
        print(f"  [{i}/{len(states)}] {state}: {len(records)} institutions")

    # Match our schools against the index.
    matched = 0
    review_rows = []

    for s in schools:
        name = s.get("school")
        state = (s.get("state") or "").strip()
        if not name or not state:
            continue
        nn = normalize(name)
        rec = index.get(state, {}).get(nn)

        if rec is not None:
            size = rec.get("latest.student.size")
            lat = rec.get("location.lat")
            lon = rec.get("location.lon")
            s["enrollment"] = size
            s["latitude"] = lat
            s["longitude"] = lon
            # Overwrite tuition with the federal figure, but ONLY when Scorecard
            # actually has a value — never blank out an existing number.
            in_state = rec.get("latest.cost.tuition.in_state")
            out_state = rec.get("latest.cost.tuition.out_of_state")
            if in_state is not None:
                s["instate_tuition"] = in_state
            if out_state is not None:
                s["outstate_tuition"] = out_state
            matched += 1
        else:
            # No exact match — find the closest name in the same state as a suggestion.
            candidates = [orig for (norm, orig) in names_by_state.get(state, [])]
            norms = [norm for (norm, orig) in names_by_state.get(state, [])]
            close = difflib.get_close_matches(nn, norms, n=1, cutoff=0.88)
            # Reject a suggestion that introduces a distinguishing word the
            # original lacks (e.g. "...Tech", "...Community") — that's a different school.
            if close:
                own_tokens = set(nn.split())
                sugg_tokens = set(close[0].split())
                added = sugg_tokens - own_tokens
                if added & _DISTINGUISHERS:
                    close = []
            if close:
                ci = norms.index(close[0])
                suggestion = candidates[ci]
                srec = index[state][close[0]]
                review_rows.append([
                    name, state, suggestion,
                    srec.get("latest.student.size"),
                    srec.get("location.lat"),
                    srec.get("location.lon"),
                    "CLOSE MATCH — verify, then fix the name in tennis_schools.json if correct",
                ])
            else:
                review_rows.append([name, state, "", "", "", "", "NO MATCH FOUND"])

    # Back up before writing.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(HERE, f"tennis_schools.backup-{stamp}.json")
    if matched:
        import shutil
        shutil.copy2(JSON_PATH, backup)
        with open(JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(schools, f, ensure_ascii=False, indent=2)

    # Write the review file.
    try:
        with open(REVIEW_PATH, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["school", "state", "scorecard_suggestion",
                        "suggested_enrollment", "suggested_lat", "suggested_lon", "note"])
            w.writerows(review_rows)
        review_written = True
    except OSError:
        review_written = False

    print("\n" + "=" * 50)
    print(f"Matched & updated: {matched} schools")
    if review_written:
        print(f"Need review:       {len(review_rows)} schools  ->  {os.path.basename(REVIEW_PATH)}")
    else:
        print(f"Need review:       {len(review_rows)} schools")
        print(f"  (Could NOT write {os.path.basename(REVIEW_PATH)} — it's open in another program.")
        print(f"   Close it and re-run to regenerate the review list. Your JSON is already saved.)")
    if matched:
        print(f"Backup saved:      {os.path.basename(backup)}")
    print("=" * 50)
    print("\nOpen scorecard_review.csv. For 'CLOSE MATCH' rows, if the suggestion")
    print("is the right school, edit its name in tennis_schools.json to match the")
    print("Scorecard name, then run this script again to pick it up.")


if __name__ == "__main__":
    main()