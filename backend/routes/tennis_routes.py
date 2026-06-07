import json
import os
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

tennis_bp = Blueprint('tennis', __name__)

# Load tennis schools data
SCHOOLS_PATH = os.path.join(os.path.dirname(__file__), 'tennis_schools.json')

def load_schools():
    with open(SCHOOLS_PATH, 'r') as f:
        return json.load(f)

def estimate_scholarship(utr, gender, division, school):
    """Estimate scholarship range based on UTR rating"""
    base = school.get('mens_scholarship') if gender == 'male' else school.get('womens_scholarship')
    if not base:
        return None, None

    # UTR-based multiplier (higher UTR = closer to full scholarship)
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

    # Division adjustments
    if division == 'NCAA III':
        return None, None  # D3 gives no athletic scholarships
    if division == 'NAIA':
        low *= 0.8; high *= 0.9

    return round(base * low), round(base * high)


@tennis_bp.route('/api/tennis/schools', methods=['GET'])
@login_required
def get_schools():
    schools = load_schools()

    # Filters from query params
    division = request.args.get('division', '')
    state = request.args.get('state', '')
    gender = request.args.get('gender', 'male')
    search = request.args.get('search', '').lower()
    utr = request.args.get('utr', type=float)
    career_pref = request.args.get('career_pref', '')  # academic / athletic / undecided
    page = request.args.get('page', 1, type=int)

    # Filter
    filtered = []
    for s in schools:
        if division and s.get('division','') != division:
            continue
        if state and s.get('state','') != state:
            continue
        if search and search not in s.get('school','').lower():
            continue
        # Skip schools with no useful data
        if not s.get('school'):
            continue
        filtered.append(s)

    # Sort: schools with scholarship data first, then by division priority
    div_order = {'NCAA I': 0, 'NCAA II': 1, 'NAIA': 2, 'JUCO': 3, 'NCAA III': 4}
    def sort_key(s):
        has_data = 0 if s.get('mens_scholarship') or s.get('womens_scholarship') else 1
        div_score = div_order.get(s.get('division',''), 5)
        return (has_data, div_score)

    filtered.sort(key=sort_key)

    # Add scholarship estimates if UTR provided
    if utr:
        for s in filtered:
            low, high = estimate_scholarship(utr, gender, s.get('division',''), s)
            s['estimated_scholarship_low'] = low
            s['estimated_scholarship_high'] = high

    # Free tier: show 10 schools, rest are locked
    FREE_LIMIT = 10
    total = len(filtered)
    is_premium = getattr(current_user, 'is_premium', False)

    if is_premium:
        visible = filtered
        locked_count = 0
    else:
        visible = filtered[:FREE_LIMIT]
        locked_count = max(0, total - FREE_LIMIT)

    return jsonify({
        'schools': visible,
        'total': total,
        'locked_count': locked_count,
        'is_premium': is_premium,
        'free_limit': FREE_LIMIT
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
    divs = sorted(set(s.get('division','') for s in schools if s.get('division')))
    states = sorted(set(s.get('state','') for s in schools if s.get('state')))
    return jsonify({'divisions': divs, 'states': states})
