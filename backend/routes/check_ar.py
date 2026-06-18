import os, json, urllib.request, urllib.parse

key = os.getenv("SCORECARD_API_KEY", "").strip()
params = {
    "api_key": key,
    "school.state": "AR",
    "fields": "school.name,latest.student.size",
    "per_page": 100,
}
url = "https://api.data.gov/ed/collegescorecard/v1/schools?" + urllib.parse.urlencode(params)
with urllib.request.urlopen(url, timeout=30) as r:
    data = json.loads(r.read().decode())

for rec in data["results"]:
    name = rec.get("school.name") or ""
    if "southern arkansas" in name.lower():
        print(name, "|", rec.get("latest.student.size"))