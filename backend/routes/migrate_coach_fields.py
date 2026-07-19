"""
One-time migration: restructure coach data in tennis_schools.json.

Existing data is MEN'S coach info held in `coach` (name) and `phone` (which
sometimes holds a phone number and sometimes an email — legacy).

This script adds six new fields and migrates the old men's data into them:
    coach_men, coach_men_email, coach_men_phone
    coach_women, coach_women_email, coach_women_phone   (start null)

- Old `coach`  -> coach_men
- Old `phone`  -> coach_men_email if it looks like an email (contains '@'),
                  else coach_men_phone
- Women's fields start null (to be gathered later).
- Old `coach` / `phone` fields are LEFT IN PLACE as a safety net.
- Backs up the JSON (timestamped) before writing.

IMPORTANT: close tennis_schools.json in VS Code before running, or the editor
may overwrite this script's output.
"""
import json, os, shutil, datetime, sys

PATH = sys.argv[1] if len(sys.argv) > 1 else 'tennis_schools.json'

def looks_like_email(v):
    return isinstance(v, str) and '@' in v

def migrate(schools):
    stats = {'total': 0, 'men_name': 0, 'men_email': 0, 'men_phone': 0, 'phone_was_email': 0}
    for s in schools:
        stats['total'] += 1
        old_coach = s.get('coach')
        old_phone = s.get('phone')

        # New fields (only set if not already present, so re-running is safe)
        s.setdefault('coach_men', old_coach if old_coach else None)
        if old_coach:
            stats['men_name'] += 1

        # Route the old phone value
        if 'coach_men_email' not in s: s['coach_men_email'] = None
        if 'coach_men_phone' not in s: s['coach_men_phone'] = None

        if old_phone:
            if looks_like_email(old_phone):
                if not s.get('coach_men_email'):
                    s['coach_men_email'] = old_phone
                    stats['men_email'] += 1
                    stats['phone_was_email'] += 1
            else:
                if not s.get('coach_men_phone'):
                    s['coach_men_phone'] = old_phone
                    stats['men_phone'] += 1

        # Women's fields start empty
        s.setdefault('coach_women', None)
        s.setdefault('coach_women_email', None)
        s.setdefault('coach_women_phone', None)
    return stats

# --- TEST on the user's sample entry first ---
sample = {
    "school": "Concordia University-Irvine", "coach": "Mattis Le Montagner",
    "phone": "mattis.lemontagner@cui.edu", "top_lineup_utr_women": 8.2,
}
sample2 = {
    "school": "Test Real Phone", "coach": "Jane Smith",
    "phone": "(555) 123-4567",
}
test = [dict(sample), dict(sample2)]
st = migrate(test)
print("=== TEST on sample entries ===")
for t in test:
    print(json.dumps({k: t.get(k) for k in
        ['school','coach','phone','coach_men','coach_men_email','coach_men_phone',
         'coach_women','coach_women_email','coach_women_phone']}, indent=2))
print("stats:", st)
print("\nExpected: Concordia's email (in old 'phone') -> coach_men_email;")
print("          'Test Real Phone' number -> coach_men_phone; women fields null.")


# --- RUN on the real file ---
if __name__ == '__main__' and os.path.exists(PATH):
    print(f"\n=== Migrating {PATH} ===")
    # Backup first
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = f"{PATH}.backup-{ts}.json"
    shutil.copy(PATH, backup)
    print(f"Backup written: {backup}")

    with open(PATH, 'r', encoding='utf-8') as f:
        schools = json.load(f)

    stats = migrate(schools)

    with open(PATH, 'w', encoding='utf-8') as f:
        json.dump(schools, f, indent=2, ensure_ascii=False)

    print(f"Done. {stats['total']} schools processed.")
    print(f"  coach_men set:        {stats['men_name']}")
    print(f"  coach_men_email set:  {stats['men_email']}  (of which {stats['phone_was_email']} were emails stored in the old 'phone' field)")
    print(f"  coach_men_phone set:  {stats['men_phone']}")
    print(f"  women's fields: all initialized to null (to be gathered)")
    print(f"\nOld 'coach' and 'phone' fields were LEFT IN PLACE as a safety net.")
    print(f"If anything looks wrong, restore from: {backup}")
else:
    print(f"\n(No real file at '{PATH}' in this environment — run locally with your real path.)")