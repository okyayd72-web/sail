import json
import os
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from backend.app import db
import anthropic

athlete_bp = Blueprint('athlete', __name__)

SCHOOLS_PATH = os.path.join(os.path.dirname(__file__), 'tennis_schools.json')

def load_schools():
    with open(SCHOOLS_PATH, 'r') as f:
        return json.load(f)


def smart_filter(schools, utr, gpa, division_pref, gender, career_pref):
    div_map = {
        'Division I':   'NCAA I',
        'Division II':  'NCAA II',
        'Division III': 'NCAA III',
        'NAIA':         'NAIA',
        'JUCO':         'JUCO',
    }
    target_div = div_map.get(division_pref) if division_pref else None

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

        utr_range = utr_ranges.get(div, (0, 16))
        if utr_range[0] <= utr <= utr_range[1]:
            score += 30
        elif utr > utr_range[1]:
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

        avg_sat = s.get('avg_sat')
        if avg_sat and gpa:
            if avg_sat >= 1200 and gpa >= 3.5:
                score += 10
            elif avg_sat >= 1000 and gpa >= 2.8:
                score += 5
            elif avg_sat >= 1200 and gpa < 2.5:
                score -= 10

        if career_pref == 'academic':
            if avg_sat and avg_sat >= 1200:
                score += 15
            elif avg_sat and avg_sat >= 1000:
                score += 8
        elif career_pref == 'athletic':
            if div in ('NCAA I', 'NCAA II') and scholarship:
                score += 15
        elif career_pref == 'balanced':
            if avg_sat and avg_sat >= 1000 and scholarship:
                score += 10

        if s.get('coach'):
            score += 5

        scored.append((score, s))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:60]]


class AthleteProfile(db.Model):
    __tablename__ = 'athlete_profiles'
    id                  = db.Column(db.String(36), primary_key=True, default=lambda: str(__import__('uuid').uuid4()))
    user_id             = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, unique=True)
    sport               = db.Column(db.String(100))
    utr_rating          = db.Column(db.Float)
    gender              = db.Column(db.String(10))
    career_preference   = db.Column(db.String(50))
    graduation_year     = db.Column(db.Integer)
    athletic_level      = db.Column(db.String(50))
    division_preference = db.Column(db.String(50))
    gpa                 = db.Column(db.Float)
    sat_score           = db.Column(db.Integer)
    act_score           = db.Column(db.Integer)
    nationality         = db.Column(db.String(100))
    state_province      = db.Column(db.String(100))
    highlights_url      = db.Column(db.Text)
    profile_complete    = db.Column(db.Boolean, default=False)

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
            'career_preference': self.career_preference,
            'graduation_year': self.graduation_year,
            'athletic_level': self.athletic_level,
            'division_preference': self.division_preference,
            'gpa': self.gpa, 'sat_score': self.sat_score,
            'act_score': self.act_score, 'nationality': self.nationality,
            'state_province': self.state_province,
            'highlights_url': self.highlights_url,
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
    for key, val in data.items():
        if hasattr(p, key):
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
                'career_pref': p.career_preference,
            })
    except Exception:
        pass

    return jsonify({'profile': p.to_dict()})


@athlete_bp.get('/api/athlete/matches')
@login_required
def get_matches():
    return jsonify({'matches': []})


@athlete_bp.post('/api/athlete/matches/refresh')
@login_required
def refresh_matches():
    p = AthleteProfile.query.filter_by(user_id=current_user.id).first()
    if not p:
        return jsonify({'error': 'Please complete your profile first.'}), 400

    utr            = p.utr_rating or 0
    gender         = p.gender or 'male'
    gpa            = p.gpa or 0
    division_pref  = p.division_preference or ''
    nationality    = p.nationality or 'Unknown'
    career_pref    = p.career_preference or 'undecided'
    athletic_level = p.athletic_level or 'developing'

    all_schools = load_schools()
    candidates = smart_filter(all_schools, utr, gpa, division_pref, gender, career_pref)

    if not candidates:
        return jsonify({'error': 'No schools found matching your preferences. Try a different division.'}), 400

    school_lines = []
    for s in candidates:
        scholarship = s.get('mens_scholarship') if gender == 'male' else s.get('womens_scholarship')
        avg_sat = s.get('avg_sat') or '?'
        coach = s.get('coach') or 'Unknown'
        loc = f"{s.get('city','')}, {s.get('state','')}".strip(', ')
        schol_str = f"${scholarship:,.0f}" if scholarship else "No data"
        school_lines.append(
            f"- {s['school']} | {s.get('division','')} | {loc} | "
            f"Avg Scholarship: {schol_str} | Avg SAT: {avg_sat} | Coach: {coach}"
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
- Career Preference: {career_pref}
- Athletic Level: {athletic_level}

CANDIDATE SCHOOLS:
{schools_text}

Pick exactly 8 schools. Return ONLY a valid JSON array, no markdown, no explanation.
Each object must have:
- "name": exact school name (string)
- "division": division (string)
- "match_score": 0-100 (integer)
- "match_reason": one specific sentence for THIS athlete (string)
- "tags": 2-3 short tags array

Example:
[{{"name":"University of Tampa","division":"NCAA II","match_score":91,"match_reason":"UTR 9.5 matches Tampa well and strong academics suit your balanced career preference.","tags":["Balanced Program","Good Aid"]}}]"""

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
            m['avg_sat']          = school_data.get('avg_sat')
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
                'career_pref': career_pref,
                'schools': [m['name'] for m in matches],
            })
        except Exception:
            pass

        return jsonify({'matches': matches})

    except json.JSONDecodeError:
        return jsonify({'error': 'AI returned invalid data. Please try again.'}), 500
    except Exception as e:
        return jsonify({'error': f'Could not generate matches: {str(e)}'}), 500