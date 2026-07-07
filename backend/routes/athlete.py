import json
import os
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from backend.app import db, limiter
import anthropic

athlete_bp = Blueprint('athlete', __name__)

SCHOOLS_PATH = os.path.join(os.path.dirname(__file__), 'tennis_schools.json')

def load_schools():
    with open(SCHOOLS_PATH, 'r') as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────
# GEOGRAPHIC HELPERS  (metro list, distance, size buckets)
# ─────────────────────────────────────────────────────────────
import math

# Major US metros with coordinates. Single source of truth: the dashboard's
# city autocomplete fetches these via /api/athlete/metros, and matching uses
# them to turn an athlete's chosen city into coordinates. Keyed "City, ST".
METROS = {
    "New York, NY": (40.7128, -74.0060), "Los Angeles, CA": (34.0522, -118.2437),
    "Chicago, IL": (41.8781, -87.6298), "Houston, TX": (29.7604, -95.3698),
    "Phoenix, AZ": (33.4484, -112.0740), "Philadelphia, PA": (39.9526, -75.1652),
    "San Antonio, TX": (29.4241, -98.4936), "San Diego, CA": (32.7157, -117.1611),
    "Dallas, TX": (32.7767, -96.7970), "San Jose, CA": (37.3382, -121.8863),
    "Austin, TX": (30.2672, -97.7431), "Jacksonville, FL": (30.3322, -81.6557),
    "Fort Worth, TX": (32.7555, -97.3308), "Columbus, OH": (39.9612, -82.9988),
    "Charlotte, NC": (35.2271, -80.8431), "Indianapolis, IN": (39.7684, -86.1581),
    "San Francisco, CA": (37.7749, -122.4194), "Seattle, WA": (47.6062, -122.3321),
    "Denver, CO": (39.7392, -104.9903), "Washington, DC": (38.9072, -77.0369),
    "Boston, MA": (42.3601, -71.0589), "Nashville, TN": (36.1627, -86.7816),
    "El Paso, TX": (31.7619, -106.4850), "Detroit, MI": (42.3314, -83.0458),
    "Oklahoma City, OK": (35.4676, -97.5164), "Portland, OR": (45.5152, -122.6784),
    "Las Vegas, NV": (36.1699, -115.1398), "Memphis, TN": (35.1495, -90.0490),
    "Louisville, KY": (38.2527, -85.7585), "Baltimore, MD": (39.2904, -76.6122),
    "Milwaukee, WI": (43.0389, -87.9065), "Albuquerque, NM": (35.0844, -106.6504),
    "Tucson, AZ": (32.2226, -110.9747), "Fresno, CA": (36.7378, -119.7871),
    "Sacramento, CA": (38.5816, -121.4944), "Kansas City, MO": (39.0997, -94.5786),
    "Mesa, AZ": (33.4152, -111.8315), "Atlanta, GA": (33.7490, -84.3880),
    "Omaha, NE": (41.2565, -95.9345), "Colorado Springs, CO": (38.8339, -104.8214),
    "Raleigh, NC": (35.7796, -78.6382), "Long Beach, CA": (33.7701, -118.1937),
    "Virginia Beach, VA": (36.8529, -75.9780), "Miami, FL": (25.7617, -80.1918),
    "Oakland, CA": (37.8044, -122.2712), "Minneapolis, MN": (44.9778, -93.2650),
    "Tulsa, OK": (36.1540, -95.9928), "Bakersfield, CA": (35.3733, -119.0187),
    "Wichita, KS": (37.6872, -97.3301), "Arlington, TX": (32.7357, -97.1081),
    "Aurora, CO": (39.7294, -104.8319), "Tampa, FL": (27.9506, -82.4572),
    "New Orleans, LA": (29.9511, -90.0715), "Cleveland, OH": (41.4993, -81.6944),
    "Honolulu, HI": (21.3069, -157.8583), "Anaheim, CA": (33.8366, -117.9143),
    "Lexington, KY": (38.0406, -84.5037), "Stockton, CA": (37.9577, -121.2908),
    "Corpus Christi, TX": (27.8006, -97.3964), "Henderson, NV": (36.0395, -114.9817),
    "Riverside, CA": (33.9806, -117.3755), "Newark, NJ": (40.7357, -74.1724),
    "Saint Paul, MN": (44.9537, -93.0900), "Santa Ana, CA": (33.7455, -117.8677),
    "Cincinnati, OH": (39.1031, -84.5120), "Irvine, CA": (33.6846, -117.8265),
    "Orlando, FL": (28.5383, -81.3792), "Pittsburgh, PA": (40.4406, -79.9959),
    "St. Louis, MO": (38.6270, -90.1994), "Greensboro, NC": (36.0726, -79.7920),
    "Lincoln, NE": (40.8136, -96.7026), "Plano, TX": (33.0198, -96.6989),
    "Anchorage, AK": (61.2181, -149.9003), "Durham, NC": (35.9940, -78.8986),
    "Jersey City, NJ": (40.7178, -74.0431), "Chandler, AZ": (33.3062, -111.8413),
    "Madison, WI": (43.0731, -89.4012), "Buffalo, NY": (42.8864, -78.8784),
    "Lubbock, TX": (33.5779, -101.8552), "Scottsdale, AZ": (33.4942, -111.9261),
    "Reno, NV": (39.5296, -119.8138), "Glendale, AZ": (33.5387, -112.1860),
    "Norfolk, VA": (36.8508, -76.2859), "Winston-Salem, NC": (36.0999, -80.2442),
    "Chesapeake, VA": (36.7682, -76.2875), "Garland, TX": (32.9126, -96.6389),
    "Irving, TX": (32.8140, -96.9489), "Hialeah, FL": (25.8576, -80.2781),
    "Fremont, CA": (37.5485, -121.9886), "Boise, ID": (43.6150, -116.2023),
    "Richmond, VA": (37.5407, -77.4360), "Baton Rouge, LA": (30.4515, -91.1871),
    "Spokane, WA": (47.6588, -117.4260), "Des Moines, IA": (41.5868, -93.6250),
    "Tacoma, WA": (47.2529, -122.4443), "San Bernardino, CA": (34.1083, -117.2898),
    "Modesto, CA": (37.6391, -120.9969), "Fontana, CA": (34.0922, -117.4350),
    "Santa Clarita, CA": (34.3917, -118.5426), "Birmingham, AL": (33.5186, -86.8104),
    "Oxnard, CA": (34.1975, -119.1771), "Fayetteville, NC": (35.0527, -78.8784),
    "Moreno Valley, CA": (33.9425, -117.2297), "Rochester, NY": (43.1566, -77.6088),
    "Glendale, CA": (34.1425, -118.2551), "Huntington Beach, CA": (33.6595, -117.9988),
    "Salt Lake City, UT": (40.7608, -111.8910), "Grand Rapids, MI": (42.9634, -85.6681),
    "Amarillo, TX": (35.2220, -101.8313), "Yonkers, NY": (40.9312, -73.8987),
    "Aurora, IL": (41.7606, -88.3201), "Montgomery, AL": (32.3792, -86.3077),
    "Akron, OH": (41.0814, -81.5190), "Little Rock, AR": (34.7465, -92.2896),
    "Huntsville, AL": (34.7304, -86.5861), "Augusta, GA": (33.4735, -82.0105),
    "Columbus, GA": (32.4610, -84.9877), "Overland Park, KS": (38.9822, -94.6708),
    "Grand Prairie, TX": (32.7459, -96.9978), "Tallahassee, FL": (30.4383, -84.2807),
    "Knoxville, TN": (35.9606, -83.9207), "Worcester, MA": (42.2626, -71.8023),
    "Newport News, VA": (37.0871, -76.4730), "Brownsville, TX": (25.9017, -97.4975),
    "Santa Rosa, CA": (38.4404, -122.7141), "Providence, RI": (41.8240, -71.4128),
    "Fort Lauderdale, FL": (26.1224, -80.1373), "Chattanooga, TN": (35.0456, -85.3097),
    "Tempe, AZ": (33.4255, -111.9400), "Oceanside, CA": (33.1959, -117.3795),
    "Garden Grove, CA": (33.7739, -117.9414), "Cape Coral, FL": (26.5629, -81.9495),
    "Springfield, MO": (37.2090, -93.2923), "Eugene, OR": (44.0521, -123.0868),
    "Fort Collins, CO": (40.5853, -105.0844), "Pembroke Pines, FL": (26.0078, -80.2963),
    "Salem, OR": (44.9429, -123.0351), "Charleston, SC": (32.7765, -79.9311),
    "Columbia, SC": (34.0007, -81.0348), "Savannah, GA": (32.0809, -81.0912),
    "Ann Arbor, MI": (42.2808, -83.7430), "Gainesville, FL": (29.6516, -82.3248),
    "Syracuse, NY": (43.0481, -76.1474), "Dayton, OH": (39.7589, -84.1916),
    "Greenville, SC": (34.8526, -82.3940), "Tuscaloosa, AL": (33.2098, -87.5692),
    "Waco, TX": (31.5493, -97.1467), "Lansing, MI": (42.7325, -84.5555),
    "Athens, GA": (33.9519, -83.3576), "Provo, UT": (40.2338, -111.6585),
    "College Station, TX": (30.6280, -96.3344), "Boulder, CO": (40.0150, -105.2705),
    "Berkeley, CA": (37.8715, -122.2730), "Cambridge, MA": (42.3736, -71.1097),
    "Gilbert, AZ": (33.3528, -111.7890), "Frisco, TX": (33.1507, -96.8236),
}


def haversine_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance between two lat/lon points, in miles."""
    R = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def size_bucket(enrollment):
    """Map raw enrollment to Small / Medium / Large (None if unknown)."""
    if not enrollment:
        return None
    if enrollment < 5000:
        return 'Small'
    if enrollment <= 15000:
        return 'Medium'
    return 'Large'


def smart_filter(schools, utr, gpa, division_pref, gender,
                 preferred_city=None, school_size=None):
    div_map = {
        'Division I':   'NCAA I',
        'Division II':  'NCAA II',
        'Division III': 'NCAA III',
        'NAIA':         'NAIA',
        'JUCO':         'JUCO',
    }
    target_div = div_map.get(division_pref) if division_pref else None

    # Resolve the athlete's preferred city to coordinates once (None if unknown).
    pref_coords = METROS.get(preferred_city) if preferred_city else None

    utr_ranges = {
        'NCAA I':   (9.0, 16.0),
        'NCAA II':  (7.0, 12.0),
        'NCAA III': (5.0, 10.0),
        'NAIA':     (5.0, 11.0),
        'JUCO':     (3.0, 9.0),
    }

    scored = []
    for s in schools:
        if not s.get('school'):
            continue
        score = 0
        div = s.get('division', '')

        if target_div:
            if div == target_div:
                score += 40
            else:
                continue
        else:
            utr_range = utr_ranges.get(div, (0, 16))
            if utr_range[0] <= utr <= utr_range[1]:
                score += 20

        # ── UTR fit: continuous score (0-35) based on roster lineup when available,
        #    falling back to distance from division-range midpoint otherwise. ──
        utr_range = utr_ranges.get(div, (0, 16))
        top_key    = 'top_lineup_utr_men'    if gender == 'male' else 'top_lineup_utr_women'
        bottom_key = 'bottom_lineup_utr_men' if gender == 'male' else 'bottom_lineup_utr_women'
        top_utr    = s.get(top_key)
        bot_utr    = s.get(bottom_key)

        if top_utr and bot_utr and top_utr > bot_utr:
            # Lineup-based fit: score peaks when player sits in the top half of the roster
            floor = bot_utr - 0.3
            if utr < floor:
                score -= 20  # below recruitable range
            else:
                span     = top_utr - floor
                position = min(1.0, (utr - floor) / span)   # 0=floor, 1=at/above top
                # Peak at position ~0.6 (solid #2-3 player); both extremes score lower
                from_peak = abs(position - 0.6) / 0.6
                score    += round(35 * max(0.0, 1 - from_peak * 0.5))
        else:
            # Division-range midpoint: continuous proximity bonus
            lo, hi  = utr_range
            center  = (lo + hi) / 2
            if lo <= utr <= hi:
                proximity = 1.0 - abs(utr - center) / (hi - lo)
                score    += round(30 * max(0.1, proximity))
            elif utr > hi:
                score += 20
            else:
                score -= 20

        scholarship = s.get('mens_scholarship') if gender == 'male' else s.get('womens_scholarship')
        if scholarship and scholarship > 0:
            score += 15
            if scholarship > 20000:
                score += 10
            elif scholarship > 10000:
                score += 5

        avg_sat = s.get('avg_sat_total')
        if avg_sat and gpa:
            if avg_sat >= 1200 and gpa >= 3.5:
                score += 10
            elif avg_sat >= 1000 and gpa >= 2.8:
                score += 5
            elif avg_sat >= 1200 and gpa < 2.5:
                score -= 10

        # ── City proximity: closer to the athlete's preferred metro scores higher ──
        if pref_coords and s.get('latitude') is not None and s.get('longitude') is not None:
            dist = haversine_miles(pref_coords[0], pref_coords[1],
                                   s['latitude'], s['longitude'])
            s['distance_from_pref'] = round(dist)
            if dist <= 50:
                score += 20
            elif dist <= 150:
                score += 12
            elif dist <= 300:
                score += 5

        # ── School size: bonus when the school matches the athlete's size preference ──
        if school_size and school_size != 'No Preference':
            bucket = size_bucket(s.get('enrollment'))
            if bucket and bucket == school_size:
                score += 12

        if s.get('coach'):
            score += 5

        scored.append((score, s))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:60]]


class AthleteProfile(db.Model):
    __tablename__ = 'athlete_profiles'
    id                     = db.Column(db.String(36), primary_key=True, default=lambda: str(__import__('uuid').uuid4()))
    user_id                = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, unique=True)
    sport                  = db.Column(db.String(100))
    utr_rating             = db.Column(db.Float)
    gender                 = db.Column(db.String(10))
    intended_major         = db.Column(db.String(100))
    preferred_city         = db.Column(db.String(100))
    school_size_preference = db.Column(db.String(20))
    graduation_year        = db.Column(db.Integer)
    athletic_level         = db.Column(db.String(50))
    division_preference    = db.Column(db.String(50))
    gpa                    = db.Column(db.Float)
    sat_score              = db.Column(db.Integer)
    act_score              = db.Column(db.Integer)
    nationality            = db.Column(db.String(100))
    state_province         = db.Column(db.String(100))
    highlights_url         = db.Column(db.Text)
    itf_junior_rank_singles = db.Column(db.Integer)
    itf_junior_rank_doubles = db.Column(db.Integer)
    itf_junior_titles       = db.Column(db.Integer)
    atp_wta_rank_singles    = db.Column(db.Integer)
    atp_wta_rank_doubles    = db.Column(db.Integer)
    total_titles            = db.Column(db.Integer)
    best_wins               = db.Column(db.Text)
    national_achievements   = db.Column(db.Text)
    profile_complete       = db.Column(db.Boolean, default=False)

    def completion_pct(self):
        fields = [self.sport, self.graduation_year, self.athletic_level,
                  self.division_preference, self.gpa, self.nationality,
                  self.utr_rating, self.gender]
        filled = sum(1 for f in fields if f)
        return int((filled / len(fields)) * 100)

    def to_dict(self):
        return {
            'id': self.id, 'sport': self.sport,
            'utr_rating': self.utr_rating, 'gender': self.gender,
            'intended_major': self.intended_major,
            'preferred_city': self.preferred_city,
            'school_size_preference': self.school_size_preference,
            'graduation_year': self.graduation_year,
            'athletic_level': self.athletic_level,
            'division_preference': self.division_preference,
            'gpa': self.gpa, 'sat_score': self.sat_score,
            'act_score': self.act_score, 'nationality': self.nationality,
            'state_province': self.state_province,
            'highlights_url': self.highlights_url,
            'itf_junior_rank_singles': self.itf_junior_rank_singles,
            'itf_junior_rank_doubles': self.itf_junior_rank_doubles,
            'itf_junior_titles': self.itf_junior_titles,
            'atp_wta_rank_singles': self.atp_wta_rank_singles,
            'atp_wta_rank_doubles': self.atp_wta_rank_doubles,
            'total_titles': self.total_titles,
            'best_wins': self.best_wins,
            'national_achievements': self.national_achievements,
            'profile_complete': self.profile_complete,
            'completion_pct': self.completion_pct(),
        }


@athlete_bp.get('/api/athlete/profile')
@login_required
def get_profile():
    p = AthleteProfile.query.filter_by(user_id=current_user.id).first()
    return jsonify({'profile': p.to_dict() if p else None})


@athlete_bp.put('/api/athlete/profile')
@login_required
def update_profile():
    p = AthleteProfile.query.filter_by(user_id=current_user.id).first()
    if not p:
        p = AthleteProfile(user_id=current_user.id)
        db.session.add(p)

    data = request.get_json() or {}

    # Fields that must be stored as numbers (or NULL), never empty strings.
    int_fields   = {'graduation_year', 'sat_score', 'act_score',
                    'itf_junior_rank_singles', 'itf_junior_rank_doubles', 'itf_junior_titles',
                    'atp_wta_rank_singles', 'atp_wta_rank_doubles', 'total_titles'}
    float_fields = {'utr_rating', 'gpa'}

    # Only these fields may be set from the request body — protects columns like
    # user_id / id / profile_complete from being overwritten via mass assignment.
    allowed_fields = {
        'sport', 'utr_rating', 'gender', 'intended_major', 'preferred_city',
        'school_size_preference', 'graduation_year', 'athletic_level',
        'division_preference', 'gpa', 'sat_score', 'act_score', 'nationality',
        'state_province', 'highlights_url',
        'itf_junior_rank_singles', 'itf_junior_rank_doubles', 'itf_junior_titles',
        'atp_wta_rank_singles', 'atp_wta_rank_doubles', 'total_titles',
        'best_wins', 'national_achievements',
    }

    for key, val in data.items():
        if key not in allowed_fields:
            continue

        # Treat empty string / blank as "clear this field" -> None
        if val is None or (isinstance(val, str) and val.strip() == ''):
            setattr(p, key, None)
            continue

        # Coerce numeric fields; if the value isn't a valid number, clear it
        if key in int_fields:
            try:
                setattr(p, key, int(val))
            except (ValueError, TypeError):
                setattr(p, key, None)
        elif key in float_fields:
            try:
                setattr(p, key, float(val))
            except (ValueError, TypeError):
                setattr(p, key, None)
        else:
            setattr(p, key, val)

    required = ['sport', 'graduation_year', 'gpa', 'nationality',
                'athletic_level', 'division_preference', 'utr_rating', 'gender']
    p.profile_complete = all(getattr(p, f) for f in required)
    db.session.commit()

    # ── Analytics: track profile completion ──
    try:
        from backend.routes.analytics import track
        track('profile_updated', {
            'complete': p.profile_complete,
            'completion_pct': p.completion_pct(),
            'division': p.division_preference,
            'utr': p.utr_rating,
            'nationality': p.nationality,
        })
        if p.profile_complete:
            track('profile_completed', {
                'division': p.division_preference,
                'utr': p.utr_rating,
                'nationality': p.nationality,
                'intended_major': p.intended_major,
            })
    except Exception:
        pass

    return jsonify({'profile': p.to_dict()})


@athlete_bp.get('/api/athlete/matches')
@login_required
def get_matches():
    return jsonify({'matches': []})


@athlete_bp.get('/api/athlete/metros')
@login_required
def get_metros():
    """Sorted list of supported metros, for the profile city autocomplete."""
    return jsonify({'metros': sorted(METROS.keys())})


@athlete_bp.post('/api/athlete/matches/refresh')
@login_required
@limiter.limit("10 per minute")
def refresh_matches():
    p = AthleteProfile.query.filter_by(user_id=current_user.id).first()
    if not p:
        return jsonify({'error': 'Please complete your profile first.'}), 400

    utr            = p.utr_rating or 0
    gender         = p.gender or 'male'
    gpa            = p.gpa or 0
    division_pref  = p.division_preference or ''
    nationality    = p.nationality or 'Unknown'
    intended_major = p.intended_major or 'Undecided'
    school_size    = p.school_size_preference or 'No Preference'
    preferred_city = p.preferred_city or ''
    athletic_level = p.athletic_level or 'developing'

    all_schools = load_schools()
    candidates = smart_filter(all_schools, utr, gpa, division_pref, gender,
                              preferred_city=preferred_city, school_size=school_size)

    if not candidates:
        return jsonify({'error': 'No schools found matching your preferences. Try a different division.'}), 400

    school_lines = []
    top_key    = 'top_lineup_utr_men'    if gender == 'male' else 'top_lineup_utr_women'
    bottom_key = 'bottom_lineup_utr_men' if gender == 'male' else 'bottom_lineup_utr_women'
    for s in candidates:
        scholarship = s.get('mens_scholarship') if gender == 'male' else s.get('womens_scholarship')
        avg_sat = s.get('avg_sat_total') or '?'
        coach = s.get('coach') or 'Unknown'
        loc = f"{s.get('city','')}, {s.get('state','')}".strip(', ')
        schol_str = f"${scholarship:,.0f}" if scholarship else "No data"
        top_utr = s.get(top_key)
        bot_utr = s.get(bottom_key)
        if top_utr and bot_utr:
            lineup_str = f"Lineup UTR: {bot_utr:.1f}–{top_utr:.1f}"
            floor = bot_utr - 0.3
            if utr >= top_utr:
                lineup_str += " (player above lineup — impact recruit)"
            elif utr >= (bot_utr + top_utr) / 2:
                lineup_str += " (player in top half of lineup)"
            elif utr >= floor:
                lineup_str += " (player at bottom of lineup)"
            else:
                lineup_str += " (player below lineup)"
        else:
            lineup_str = "Lineup UTR: no data"
        school_lines.append(
            f"- {s['school']} | {s.get('division','')} | {loc} | "
            f"Avg Scholarship: {schol_str} | {lineup_str} | Avg SAT: {avg_sat} | Coach: {coach}"
        )

    schools_text = '\n'.join(school_lines)

    prompt = f"""You are an expert college tennis recruiting advisor.
Your job is to recommend the 8 best-fit schools for this specific athlete from the list below.

ATHLETE PROFILE:
- UTR Rating: {utr} (Universal Tennis Rating, scale 1-16)
- Gender: {gender}
- GPA: {gpa}
- Division Preference: {division_pref or 'No preference'}
- Nationality: {nationality}
- Intended Major: {intended_major}
- School Size Preference: {school_size}
- Preferred City/Region: {preferred_city or 'No preference'}
- Athletic Level: {athletic_level}

CANDIDATE SCHOOLS:
{schools_text}

Note: SAT values shown are the school's average composite SAT score (Math + Critical Reading). Schools showing "?" have no SAT data available.

Pick exactly 8 schools. Return ONLY a valid JSON array, no markdown, no explanation.
Each object must have:
- "name": exact school name (string)
- "division": division (string)
- "match_score": 0-100 (integer)
- "match_reason": one specific sentence for THIS athlete (string)
- "tags": 2-3 short tags array

Example:
[{{"name":"University of Tampa","division":"NCAA II","match_score":91,"match_reason":"UTR 9.5 matches Tampa well and a Business major fits their strong academic programs.","tags":["Strong Academics","Good Aid"]}}]"""

    try:
        client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        message = client.messages.create(
            model='claude-haiku-4-5',
            max_tokens=2000,
            messages=[{'role': 'user', 'content': prompt}]
        )

        raw = message.content[0].text.strip()
        if '```' in raw:
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]
        raw = raw.strip()

        matches = json.loads(raw)

        school_lookup = {s['school'].lower(): s for s in all_schools}
        for m in matches:
            school_data = school_lookup.get(m['name'].lower(), {})
            scholarship = school_data.get('mens_scholarship') if gender == 'male' else school_data.get('womens_scholarship')
            m['location']         = f"{school_data.get('city','')}, {school_data.get('state','')}".strip(', ')
            m['outstate_tuition'] = school_data.get('outstate_tuition')
            m['avg_sat']          = school_data.get('avg_sat_total')
            m['coach']            = school_data.get('coach')
            m['phone']            = school_data.get('phone')
            m['avg_scholarship']  = scholarship

        # ── Analytics: track match generation ──
        try:
            from backend.routes.analytics import track
            track('match_generated', {
                'utr': utr,
                'gender': gender,
                'division': division_pref,
                'nationality': nationality,
                'intended_major': intended_major,
                'schools': [m['name'] for m in matches],
            })
        except Exception:
            pass

        return jsonify({'matches': matches})

    except json.JSONDecodeError:
        return jsonify({'error': 'AI returned invalid data. Please try again.'}), 500
    except Exception as e:
        return jsonify({'error': f'Could not generate matches: {str(e)}'}), 500