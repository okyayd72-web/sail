import json

with open('backend/routes/tennis_schools.json', 'r') as f:
    schools = json.load(f)

for school in schools:
    # Remove old fields
    school.pop('avg_team_utr_men', None)
    school.pop('avg_team_utr_women', None)
    
    # Add new fields (keep top/bottom lineup as they are)
    school['power6_utr_men'] = None
    school['power6_utr_women'] = None

with open('backend/routes/tennis_schools.json', 'w') as f:
    json.dump(schools, f, indent=2)

print(f"✅ Updated {len(schools)} schools with power6 fields")