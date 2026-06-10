import json
import os
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

tennis_bp = Blueprint('tennis', __name__)

SCHOOLS_PATH = os.path.join(os.path.dirname(__file__), 'tennis_schools.json')

# ── BETA MODE: All users get full access ──
BETA_MODE = True

def load_schools():
    with open(SCHOOLS_PATH, 'r') as f:
        return json.load(f)


def estimate_scholarship(utr, gender, division, school):
    base = school.get('mens_scholarship') if gender == 'male' else school.get('womens_scholarship')
    if not base:
        return None, None

    # Women's UTR max is ~13, men's is 16
    max_utr = 13.0 if gender == 'female' else 16.0
    utr = min(utr, max_utr)

    if utr >= 13:
        low, high = 0.75, 1.0
    elif utr >= 11:
        low, high = 0.50, 0.80
    elif utr >= 9:
        low, high = 0.30, 0.60
    elif utr >= 7:
        low, high = 0.15, 0.40
    elif utr >= 5:
        low, high = 0.05, 0.20
    else:
        low, high = 0.0, 0.10

    if division == 'NCAA III':
        return None, None   # No athletic scholarships in D3
    if division == 'NAIA':
        low *= 0.8
        high *= 0.9

    return round(base * low), round(base * high)


@tennis_bp.route('/api/tennis/schools', methods=['GET'])
@login_required
def get_schools():
    # ── Analytics: track school page view ──
    try:
        from backend.routes.analytics import track
        track('school_page_viewed', {
            'division': request.args.get('division', ''),
            'state': request.args.get('state', ''),
            'gender': request.args.get('gender', 'male'),
        })
    except Exception:
        pass

    schools = load_schools()

    division = request.args.get('division', '')
    state    = request.args.get('state', '')
    gender   = request.args.get('gender', 'male')
    search   = request.args.get('search', '').lower()
    utr      = request.args.get('utr', type=float)

    filtered = []
    for s in schools:
        if division and s.get('division', '') != division:
            continue
        if state and s.get('state', '') != state:
            continue
        if search and search not in s.get('school', '').lower():
            continue
        if not s.get('school'):
            continue
        filtered.append(s)

    div_order = {'NCAA I': 0, 'NCAA II': 1, 'NAIA': 2, 'JUCO': 3, 'NCAA III': 4}
    def sort_key(s):
        has_data = 0 if s.get('mens_scholarship') or s.get('womens_scholarship') else 1
        div_score = div_order.get(s.get('division', ''), 5)
        return (has_data, div_score)

    filtered.sort(key=sort_key)

    if utr:
        for s in filtered:
            low, high = estimate_scholarship(utr, gender, s.get('division', ''), s)
            s['estimated_scholarship_low']  = low
            s['estimated_scholarship_high'] = high

    total = len(filtered)

    # ── BETA MODE: show all schools, no paywall ──
    if BETA_MODE:
        visible      = filtered
        locked_count = 0
        is_premium   = True
    else:
        FREE_LIMIT = 10
        is_premium = getattr(current_user, 'is_premium', False)
        if is_premium:
            visible      = filtered
            locked_count = 0
        else:
            visible      = filtered[:FREE_LIMIT]
            locked_count = max(0, total - FREE_LIMIT)

    return jsonify({
        'schools':      visible,
        'total':        total,
        'locked_count': locked_count,
        'is_premium':   is_premium,
        'beta_mode':    BETA_MODE,
    })


@tennis_bp.route('/api/tennis/schools/<school_name>', methods=['GET'])
@login_required
def get_school_detail(school_name):
    schools = load_schools()
    school = next((s for s in schools if s['school'].lower() == school_name.lower()), None)
    if not school:
        return jsonify({'error': 'School not found'}), 404
    return jsonify({'school': school})


@tennis_bp.route('/api/tennis/divisions', methods=['GET'])
@login_required
def get_divisions():
    schools = load_schools()
    divs   = sorted(set(s.get('division', '') for s in schools if s.get('division')))
    states = sorted(set(s.get('state', '') for s in schools if s.get('state')))
    return jsonify({'divisions': divs, 'states': states})