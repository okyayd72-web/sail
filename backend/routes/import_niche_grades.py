"""
import_niche_grades.py
-----------------------
Step 2 of 2. Reads your filled-in niche_grades.csv and writes the grades
back into tennis_schools.json.

It is SAFE:
  - It backs up tennis_schools.json before changing anything.
  - It validates every grade and refuses to write anything invalid.
  - It only touches the 'niche_grade' field; every other value is left alone.
  - Blank rows are skipped, so a half-finished CSV is fine.

HOW TO RUN (Windows PowerShell):
    1. Keep this file in the SAME folder as tennis_schools.json and niche_grades.csv
    2. Run:  python import_niche_grades.py
    3. Read the summary it prints.
"""

import csv
import json
import os
import shutil
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(HERE, "tennis_schools.json")
CSV_PATH = os.path.join(HERE, "niche_grades.csv")

VALID_GRADES = {
    "A+", "A", "A-",
    "B+", "B", "B-",
    "C+", "C", "C-",
    "D+", "D", "D-",
    "F",
}


def normalize_grade(raw):
    """Clean up whatever was typed: trim, uppercase, and fix non-ASCII dashes."""
    if raw is None:
        return ""
    g = raw.strip().upper()
    for dash in ("\u2212", "\u2013", "\u2014", "\u2010"):  # minus, en/em dash, hyphen
        g = g.replace(dash, "-")
    return g.replace(" ", "")


def main():
    if not os.path.exists(JSON_PATH):
        print(f"ERROR: tennis_schools.json not found at {JSON_PATH}")
        return
    if not os.path.exists(CSV_PATH):
        print(f"ERROR: niche_grades.csv not found at {CSV_PATH}")
        print("       Run export_niche_template.py first, then fill it in.")
        return

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        schools = json.load(f)

    # Look up schools by exact name (the CSV was generated from these names).
    by_name = {s.get("school"): s for s in schools if s.get("school")}

    updated = 0
    unchanged = 0
    blanks = 0
    invalid = []     # (school, bad_grade)
    unmatched = []   # school names in CSV not found in JSON

    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("school") or "").strip()
            grade = normalize_grade(row.get("niche_grade"))

            if not name:
                continue
            if not grade:
                blanks += 1
                continue
            if grade not in VALID_GRADES:
                invalid.append((name, row.get("niche_grade")))
                continue

            school = by_name.get(name)
            if school is None:
                unmatched.append(name)
                continue

            if school.get("niche_grade") == grade:
                unchanged += 1
            else:
                school["niche_grade"] = grade
                updated += 1

    # ── Nothing valid to write? Stop before backing up or saving. ──
    if updated == 0:
        print("No changes made.")
        if blanks:
            print(f"  - {blanks} blank rows skipped (no grade entered yet).")
        if unchanged:
            print(f"  - {unchanged} rows already matched what's in the JSON.")
        _report_problems(invalid, unmatched)
        return

    # ── Back up, then save ──
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(HERE, f"tennis_schools.backup-{stamp}.json")
    shutil.copy2(JSON_PATH, backup)

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(schools, f, ensure_ascii=False, indent=2)

    print("Success!")
    print(f"  - Updated {updated} school grade(s).")
    if unchanged:
        print(f"  - {unchanged} already matched (left as-is).")
    if blanks:
        print(f"  - {blanks} blank rows skipped.")
    print(f"  - Backup of your original saved as: {os.path.basename(backup)}")
    _report_problems(invalid, unmatched)


def _report_problems(invalid, unmatched):
    if invalid:
        print()
        print(f"WARNING: {len(invalid)} row(s) had an invalid grade and were skipped:")
        for name, bad in invalid[:20]:
            print(f"     '{bad}'  for  {name}")
        if len(invalid) > 20:
            print(f"     ...and {len(invalid) - 20} more.")
        print("   Valid grades: A+ A A- B+ B B- C+ C C- D+ D D- F")
    if unmatched:
        print()
        print(f"WARNING: {len(unmatched)} school name(s) in the CSV were not found in the JSON:")
        for name in unmatched[:20]:
            print(f"     {name}")
        if len(unmatched) > 20:
            print(f"     ...and {len(unmatched) - 20} more.")
        print("   These are usually caused by editing the 'school' column. Don't change school names in the CSV.")


if __name__ == "__main__":
    main()