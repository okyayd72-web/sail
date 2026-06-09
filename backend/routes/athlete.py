import json
import os
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from backend.app import db
import anthropic

athlete_bp = Blueprint('athlete', __name__)

# Load tennis schools once at startup
SCHOOLS_PATH = os.path.join(os.path.dirname(__file__), 'tennis_schools.json')
def load_schools():
    with open(SCHOOLS_PATH, 'r') as f:
        return json.load(f)


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
    return jsonify({'profile': p.to_dict()})


@athlete_bp.get('/api/athlete/matches')
@login_required
def get_matches():
    # Return cached matches from session/db if available
    # For now return empty — matches are generated on refresh
    return jsonify({'matches': []})


@athlete_bp.post('/api/athlete/matches/refresh')
@login_required
def refresh_matches():
    p = AthleteProfile.query.filter_by(user_id=current_user.id).first()
    if not p:
        return jsonify({'error': 'Please complete your profile first.'}), 400

    # Build profile summary for AI
    utr = p.utr_rating or 0
    gender = p.gender or 'male'
    gpa = p.gpa or 0
    division_pref = p.division_preference or 'Any'
    nationality = p.nationality or 'Unknown'
    career_pref = p.career_preference or 'undecided'
    athletic_level = p.athletic_level or 'developing'

    # Filter schools from database
    all_schools = load_schools()

    # Filter by division preference
    div_map = {
        'Division I': 'NCAA I',
        'Division II': 'NCAA II',
        'Division III': 'NCAA III',
        'NAIA': 'NAIA',
        'JUCO': 'JUCO',
    }
    target_div = div_map.get(division_pref)

    candidates = []
    for s in all_schools:
        if target_div and s.get('division') != target_div:
            continue
        # Only include schools with some data
        if not s.get('school'):
            continue
        candidates.append(s)

    # Sort: schools with scholarship data first
    candidates.sort(key=lambda s: 0 if s.get('mens_scholarship') or s.get('womens_scholarship') else 1)

    # Take top 30 candidates for AI to choose from
    top_candidates = candidates[:30]

    # Build a compact school list for the AI prompt
    school_list = []
    for s in top_candidates:
        scholarship = s.get('mens_scholarship') if gender == 'male' else s.get('womens_scholarship')
        school_list.append(
            f"- {s['school']} ({s.get('division','')}, {s.get('state','')}) | "
            f"Avg Scholarship: ${scholarship:,.0f}" if scholarship else
            f"- {s['school']} ({s.get('division','')}, {s.get('state','')}) | No scholarship data"
        )

    schools_text = '\n'.join(school_list)

    prompt = f"""You are a college tennis recruiting advisor. Based on the following student-athlete profile, recommend exactly 8 schools from the list below that would be the best fit.

ATHLETE PROFILE:
- UTR Rating: {utr}
- Gender: {gender}
- GPA: {gpa}
- Division Preference: {division_pref}
- Nationality: {nationality}
- Career Preference: {career_pref} (academic = wants strong academics, athletic = wants best tennis program, balanced = both matter)
- Athletic Level: {athletic_level}

AVAILABLE SCHOOLS:
{schools_text}

Return ONLY a JSON array of exactly 8 objects. No explanation, no markdown, just the raw JSON array.
Each object must have these exact fields:
- "name": school name (string)
- "division": division (string)  
- "match_score": fit score 0-100 (integer)
- "match_reason": one sentence explaining why this school fits this athlete (string)
- "tags": array of 2-3 short tags like ["Strong Academics", "International Friendly", "Good Aid"]

Example format:
[{{"name":"University of Example","division":"NCAA I","match_score":88,"match_reason":"Strong tennis program with good scholarship history for UTR 8+ players.","tags":["Good Aid","Competitive Program"]}}]"""

    try:
        client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        message = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=1500,
            messages=[{'role': 'user', 'content': prompt}]
        )

        raw = message.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]
        raw = raw.strip()

        matches = json.loads(raw)

        # Enrich matches with school data from our database
        school_lookup = {s['school'].lower(): s for s in all_schools}
        for m in matches:
            school_data = school_lookup.get(m['name'].lower(), {})
            scholarship = school_data.get('mens_scholarship') if gender == 'male' else school_data.get('womens_scholarship')
            m['location'] = f"{school_data.get('city','')}, {school_data.get('state','')}".strip(', ')
            m['outstate_tuition'] = school_data.get('outstate_tuition')
            m['avg_sat'] = school_data.get('avg_sat')
            m['coach'] = school_data.get('coach')
            m['phone'] = school_data.get('phone')
            m['avg_scholarship'] = scholarship

        return jsonify({'matches': matches})

    except json.JSONDecodeError:
        return jsonify({'error': 'AI returned invalid data. Please try again.'}), 500
    except Exception as e:
        return jsonify({'error': f'Could not generate matches: {str(e)}'}), 500