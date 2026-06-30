import json
import os
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from backend.app import db

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


def estimate_scholarship_v2(utr, gender, school):
    """Roster-lineup-based scholarship estimate.

    Returns:
        ('unlikely', None) — player UTR is below the recruitable floor
        (None, None)       — school is missing lineup or scholarship data; caller
                             should fall back to estimate_scholarship()
        (low, high)        — estimated dollar range
    """
    top_key    = 'top_lineup_utr_men'    if gender == 'male' else 'top_lineup_utr_women'
    bottom_key = 'bottom_lineup_utr_men' if gender == 'male' else 'bottom_lineup_utr_women'
    avg_key    = 'mens_scholarship'      if gender == 'male' else 'womens_scholarship'

    top    = school.get(top_key)
    bottom = school.get(bottom_key)
    avg    = school.get(avg_key)

    if top is None or bottom is None or not avg or avg <= 0:
        return None, None  # no lineup data — caller falls back to v1

    floor = bottom - 0.3
    if top <= floor:
        return None, None  # degenerate data — avoid divide-by-zero

    if utr < floor:
        return 'unlikely', None  # not recruitable at this school

    position   = (utr - floor) / (top - floor)
    position   = max(0.0, min(1.0, position))
    multiplier = 0.5 + 0.9 * position          # 0.5 (bottom of lineup) → 1.4 (top/above)
    estimate   = avg * multiplier
    return round(estimate * 0.9), round(estimate * 1.1)


# UTR ranges per division — defined at module level so both functions can use it
UTR_RANGES = {
    'NCAA I':   (9.0, 16.0),
    'NCAA II':  (7.0, 12.0),
    'NCAA III': (5.0, 10.0),
    'NAIA':     (5.0, 11.0),
    'JUCO':     (3.0, 9.0),
    'CCCAA':    (3.0, 9.0),
    'USCAA':    (3.0, 9.0),
    'NWAC':     (3.0, 9.0),
    'NCCAA':    (4.0, 10.0),
}

# Niche letter grades ranked best → worst, for the "minimum grade" filter.
# JSON values must match these keys exactly (capital letter, ASCII hyphen): "A+", "A", "A-", ...
GRADE_RANK = {
    'A+': 13, 'A': 12, 'A-': 11,
    'B+': 10, 'B': 9,  'B-': 8,
    'C+': 7,  'C': 6,  'C-': 5,
    'D+': 4,  'D': 3,  'D-': 2,
    'F':  1,
}


def utr_fit_score(division, utr_val):
    """Returns 0 for perfect fit, higher = worse fit.
    - In-range schools score 0 to ~0.5 (closer to the middle = better).
    - Below range (a reach school for the player) scores 1+.
    - Above range (player is overqualified) scales with how far above, so schools
      the player has clearly outgrown sink down the list instead of mixing in.
    - Unknown divisions sink to the bottom."""
    if not utr_val:
        return 0
    r = UTR_RANGES.get(division)
    if r is None:
        return 5.0  # division we don't have a range for -> rank last
    if r[0] <= utr_val <= r[1]:
        center = (r[0] + r[1]) / 2
        return abs(utr_val - center) / (r[1] - r[0])
    elif utr_val < r[0]:
        return 1 + (r[0] - utr_val)
    else:
        return 1 + (utr_val - r[1])

def get_avg_utrs(school):
    """Convert Power 6 totals to averages"""
    power6_men   = school.get('power6_utr_men')
    power6_women = school.get('power6_utr_women')
    return {
        'avg_utr_men':   round(power6_men   / 6, 2) if power6_men   else None,
        'avg_utr_women': round(power6_women / 6, 2) if power6_women else None,
    }


# ─────────────────────────────────────────────────────────────
# LANDING-PAGE PREVIEW (public teaser)
# ─────────────────────────────────────────────────────────────

@tennis_bp.route('/api/tennis/preview', methods=['GET'])
def get_preview():
    """Public landing-page teaser. Uses ACTUAL roster data: a school's "level" is its
    Power 6 average (power6_utr / 6). Shows schools whose level is within +/-1.0 of the
    player's UTR, ranked by scholarship-to-tuition ratio (capped at 100%), with UTR
    closeness as the tiebreaker. Because the window slides with the player's UTR, the
    schools genuinely change across UTR levels. Only schools with roster data appear.
    Separate from get_schools so the main Find Schools page is untouched."""
    schools = load_schools()

    gender = request.args.get('gender', 'male')
    utr    = request.args.get('utr', type=float)
    WINDOW = 1.0

    if utr is not None:
        utr = min(utr, 13.0 if gender == 'female' else 16.0)

    power6_f = 'power6_utr_men'   if gender == 'male' else 'power6_utr_women'
    schol_f  = 'mens_scholarship' if gender == 'male' else 'womens_scholarship'

    matches = []
    for s in schools:
        if not s.get('school'):
            continue
        power6 = s.get(power6_f)
        if not power6:
            continue  # no roster data -> can't place player -> skip
        level = power6 / 6.0

        # Fit: school's average roster level within +/-WINDOW of the player's UTR.
        if utr is not None and abs(level - utr) > WINDOW:
            continue

        schol = s.get(schol_f)
        tuition = s.get('outstate_tuition') or s.get('instate_tuition')
        if not schol or not tuition or tuition <= 0:
            continue  # need both to compute a value ratio

        ratio     = min(schol / tuition, 1.0)               # cap at 100%
        closeness = abs(level - utr) if utr is not None else 0.0
        # Rank: best value first (-ratio), ties broken by closeness to player's UTR.
        matches.append((-ratio, closeness, s))

    matches.sort(key=lambda x: (x[0], x[1]))
    top6 = [s for _, _, s in matches[:6]]

    return jsonify({
        'schools': top6,
        'total':   len(matches),
    })


# ─────────────────────────────────────────────────────────────
# FAVORITES
# ─────────────────────────────────────────────────────────────

class FavoriteSchool(db.Model):
    __tablename__ = 'favorite_schools'
    id          = db.Column(db.String(36), primary_key=True, default=lambda: str(__import__('uuid').uuid4()))
    user_id     = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    school_name = db.Column(db.String(200), nullable=False)
    created_at  = db.Column(db.DateTime, server_default=db.func.now())

    __table_args__ = (
        db.UniqueConstraint('user_id', 'school_name', name='uq_user_school'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'school_name': self.school_name,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


def can_use_favorites():
    """Saving schools is a paid-tier feature. During beta, everyone has access."""
    if BETA_MODE:
        return True
    return getattr(current_user, 'is_premium', False)


@tennis_bp.route('/api/tennis/favorites', methods=['GET'])
@login_required
def list_favorites():
    favs = (FavoriteSchool.query
            .filter_by(user_id=current_user.id)
            .order_by(FavoriteSchool.created_at.desc())
            .all())
    fav_names = [f.school_name for f in favs]

    # Hydrate full school objects from the JSON so the frontend can render cards
    schools = load_schools()
    lookup = {s['school']: s for s in schools if s.get('school')}

    hydrated = []
    for f in favs:
        base = lookup.get(f.school_name)
        if not base:
            continue  # school may have been removed from the JSON since it was saved
        s = dict(base)  # copy so we never mutate the loaded list
        utrs = get_avg_utrs(s)
        s['avg_utr_men']   = utrs['avg_utr_men']
        s['avg_utr_women'] = utrs['avg_utr_women']
        s['favorited_at']  = f.created_at.isoformat() if f.created_at else None
        hydrated.append(s)

    return jsonify({
        'favorites': fav_names,   # list of saved school names (for marking hearts)
        'schools':   hydrated,    # full objects (for the "Saved" view)
        'count':     len(fav_names),
    })


@tennis_bp.route('/api/tennis/favorites', methods=['POST'])
@login_required
def add_favorite():
    if not can_use_favorites():
        return jsonify({'error': 'Saving schools is a Premium feature.', 'upgrade': True}), 403

    data = request.get_json() or {}
    school_name = (data.get('school_name') or '').strip()
    if not school_name:
        return jsonify({'error': 'school_name is required.'}), 400

    # Validate the school actually exists in our data
    schools = load_schools()
    if not any(s.get('school') == school_name for s in schools):
        return jsonify({'error': 'School not found.'}), 404

    existing = FavoriteSchool.query.filter_by(user_id=current_user.id, school_name=school_name).first()
    if existing:
        return jsonify({'favorited': True, 'school_name': school_name, 'message': 'Already saved.'}), 200

    fav = FavoriteSchool(user_id=current_user.id, school_name=school_name)
    try:
        db.session.add(fav)
        db.session.commit()
    except Exception:
        # Unique-constraint backstop in case of a race; treat as already saved
        db.session.rollback()
        return jsonify({'favorited': True, 'school_name': school_name, 'message': 'Already saved.'}), 200

    # ── Analytics ──
    try:
        from backend.routes.analytics import track
        track('school_favorited', {'school': school_name})
    except Exception:
        pass

    return jsonify({'favorited': True, 'school_name': school_name}), 201


@tennis_bp.route('/api/tennis/favorites/<path:school_name>', methods=['DELETE'])
@login_required
def remove_favorite(school_name):
    if not can_use_favorites():
        return jsonify({'error': 'Saving schools is a Premium feature.', 'upgrade': True}), 403

    fav = FavoriteSchool.query.filter_by(user_id=current_user.id, school_name=school_name).first()
    if not fav:
        return jsonify({'favorited': False, 'school_name': school_name, 'message': 'Not in favorites.'}), 200

    db.session.delete(fav)
    db.session.commit()

    # ── Analytics ──
    try:
        from backend.routes.analytics import track
        track('school_unfavorited', {'school': school_name})
    except Exception:
        pass

    return jsonify({'favorited': False, 'school_name': school_name}), 200


# ─────────────────────────────────────────────────────────────
# SCHOOLS
# ─────────────────────────────────────────────────────────────

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
    niche_min = request.args.get('niche_min', '').strip()

    # ── Filter ──
    filtered = []
    for s in schools:
        if division and s.get('division', '') != division:
            continue
        if state and s.get('state', '') != state:
            continue
        if search and search not in s.get('school', '').lower():
            continue
        if niche_min:
            g = (s.get('niche_grade') or '').strip()
            if not g or GRADE_RANK.get(g, 0) < GRADE_RANK.get(niche_min, 0):
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
            low, high = estimate_scholarship_v2(utr, gender, s)
            if low is None and high is None:
                # No lineup data — fall back to division-bracket estimate
                low, high = estimate_scholarship(utr, gender, s.get('division', ''), s)
                s['scholarship_unlikely']       = False
            elif low == 'unlikely':
                low, high                       = None, None
                s['scholarship_unlikely']       = True
            else:
                s['scholarship_unlikely']       = False
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


@tennis_bp.route('/api/tennis/school-names', methods=['GET'])
@login_required
def get_school_names():
    schools = load_schools()
    names   = sorted(s['school'] for s in schools if s.get('school'))
    return jsonify({'names': names})


@tennis_bp.route('/api/tennis/compare', methods=['POST'])
@login_required
def compare_schools():
    data   = request.get_json() or {}
    name1  = data.get('school1', '').strip()
    name2  = data.get('school2', '').strip()
    offer1 = data.get('offer1', 0)
    offer2 = data.get('offer2', 0)
    gender = data.get('gender', 'male')

    if not name1 or not name2:
        return jsonify({'error': 'Two school names are required.'}), 400

    try:
        from backend.routes.athlete import AthleteProfile
        profile    = AthleteProfile.query.filter_by(user_id=current_user.id).first()
        player_utr = profile.utr_rating if profile else None
        if not gender and profile:
            gender = profile.gender or 'male'
    except Exception:
        player_utr = None

    schools = load_schools()
    lookup  = {s['school'].lower(): s for s in schools}
    s1      = lookup.get(name1.lower())
    s2      = lookup.get(name2.lower())

    if not s1:
        return jsonify({'error': f'School not found: {name1}'}), 404
    if not s2:
        return jsonify({'error': f'School not found: {name2}'}), 404

    def build_side(school, offer_amount):
        offer   = float(offer_amount) if offer_amount else 0
        tuition = school.get('outstate_tuition') or school.get('instate_tuition')

        if tuition and tuition > 0:
            coverage_pct = min(100, round(offer / tuition * 100))
            coverage_str = f"${offer:,.0f} covers {coverage_pct}% of ${tuition:,} tuition"
        else:
            coverage_pct = None
            coverage_str = "Tuition data not available"

        top_key    = 'top_lineup_utr_men'    if gender == 'male' else 'top_lineup_utr_women'
        bottom_key = 'bottom_lineup_utr_men' if gender == 'male' else 'bottom_lineup_utr_women'
        top_utr    = school.get(top_key)
        bot_utr    = school.get(bottom_key)

        if top_utr and bot_utr:
            lineup_range = f"{bot_utr:.1f}–{top_utr:.1f}"
            if player_utr:
                mid = (top_utr + bot_utr) / 2
                if player_utr >= top_utr:
                    lineup_label = "Above current lineup — impact recruit"
                    lineup_pos   = "top"
                elif player_utr >= mid:
                    lineup_label = "Top half of lineup (~positions 1–3)"
                    lineup_pos   = "upper"
                elif player_utr >= bot_utr - 0.3:
                    lineup_label = "Bottom half of lineup (~positions 4–6)"
                    lineup_pos   = "lower"
                else:
                    lineup_label = "Below current lineup"
                    lineup_pos   = "below"
            else:
                lineup_label = "Set your UTR in your profile to see lineup fit"
                lineup_pos   = None
        else:
            lineup_range = None
            lineup_label = "Lineup data not yet available for this school"
            lineup_pos   = None

        avg_schol = school.get('mens_scholarship') if gender == 'male' else school.get('womens_scholarship')

        return {
            'name':          school.get('school'),
            'division':      school.get('division'),
            'city':          school.get('city'),
            'state':         school.get('state'),
            'offer':         offer,
            'tuition':       tuition,
            'coverage_pct':  coverage_pct,
            'coverage_str':  coverage_str,
            'lineup_range':  lineup_range,
            'lineup_label':  lineup_label,
            'lineup_pos':    lineup_pos,
            'has_lineup':    bool(top_utr and bot_utr),
            'avg_scholarship': avg_schol,
            'niche_grade':   school.get('niche_grade'),
        }

    return jsonify({
        'player_utr': player_utr,
        'gender':     gender,
        'school1':    build_side(s1, offer1),
        'school2':    build_side(s2, offer2),
    })


@tennis_bp.route('/api/tennis/divisions', methods=['GET'])
def get_divisions():
    schools = load_schools()
    divs    = sorted(set(s.get('division', '') for s in schools if s.get('division')))
    states  = sorted(set(s.get('state', '')    for s in schools if s.get('state')))
    return jsonify({'divisions': divs, 'states': states})