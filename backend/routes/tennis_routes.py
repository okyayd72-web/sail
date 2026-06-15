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
        return None, None
    if division == 'NAIA':
        low *= 0.8
        high *= 0.9

    return round(base * low), round(base * high)


# UTR ranges per division — defined at module level so both functions can use it
UTR_RANGES = {
    'NCAA I':   (9.0, 16.0),
    'NCAA II':  (7.0, 12.0),
    'NCAA III': (5.0, 10.0),
    'NAIA':     (5.0, 11.0),
    'JUCO':     (3.0, 9.0),
}


def utr_fit_score(division, utr_val):
    """Returns 0 for perfect fit, higher = worse fit"""
    if not utr_val:
        return 0
    r = UTR_RANGES.get(division, (0, 16))
    if r[0] <= utr_val <= r[1]:
        center = (r[0] + r[1]) / 2
        return abs(utr_val - center) / (r[1] - r[0])
    elif utr_val < r[0]:
        return 1 + (r[0] - utr_val)
    else:
        return 0.5

def get_avg_utrs(school):         
    """Convert Power 6 totals to averages"""
    power6_men   = school.get('power6_utr_men')
    power6_women = school.get('power6_utr_women')
    return {
        'avg_utr_men':   round(power6_men   / 6, 2) if power6_men   else None,
        'avg_utr_women': round(power6_women / 6, 2) if power6_women else None,
    }


@tennis_bp.route('/api/tennis/schools', methods=['GET'])
def get_schools():
    # ── Analytics ──
    try:
        from backend.routes.analytics import track
        track('school_page_viewed', {
            'division': request.args.get('division', ''),
            'state':    request.args.get('state', ''),
            'gender':   request.args.get('gender', 'male'),
        })
    except Exception:
        pass

    schools = load_schools()

    division = request.args.get('division', '')
    state    = request.args.get('state', '')
    gender   = request.args.get('gender', 'male')
    search   = request.args.get('search', '').lower()
    utr      = request.args.get('utr', type=float)

    # ── Filter ──
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

    # ── Sort by UTR fit ──
    def sort_key(s):
        fit      = utr_fit_score(s.get('division', ''), utr)
        has_data = 0 if s.get('mens_scholarship') or s.get('womens_scholarship') else 1
        return (round(fit, 3), has_data)

    filtered.sort(key=sort_key)

    # ── Add scholarship estimates ──
    if utr:
        for s in filtered:
            low, high = estimate_scholarship(utr, gender, s.get('division', ''), s)
            s['estimated_scholarship_low']  = low
            s['estimated_scholarship_high'] = high

    total = len(filtered)

    # ── Beta mode: show all schools ──
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
    
    for s in visible:
        utrs = get_avg_utrs(s)
        s['avg_utr_men']   = utrs['avg_utr_men']
        s['avg_utr_women'] = utrs['avg_utr_women']

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
    school  = next((s for s in schools if s['school'].lower() == school_name.lower()), None)
    if not school:
        return jsonify({'error': 'School not found'}), 404
    return jsonify({'school': school})


@tennis_bp.route('/api/tennis/divisions', methods=['GET'])
def get_divisions():
    schools = load_schools()
    divs    = sorted(set(s.get('division', '') for s in schools if s.get('division')))
    states  = sorted(set(s.get('state', '')    for s in schools if s.get('state')))
    return jsonify({'divisions': divs, 'states': states})