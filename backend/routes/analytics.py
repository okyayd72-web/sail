import json
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from backend.app import db

analytics_bp = Blueprint('analytics', __name__)

# ── Analytics Event Model ──
class AnalyticsEvent(db.Model):
    __tablename__ = 'analytics_events'

    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id    = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)
    event_type = db.Column(db.String(100), nullable=False)
    event_data = db.Column(db.Text, nullable=True)   # JSON string
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':         self.id,
            'user_id':    self.user_id,
            'event_type': self.event_type,
            'event_data': json.loads(self.event_data) if self.event_data else {},
            'created_at': self.created_at.isoformat(),
        }


def track(event_type, data=None, user_id=None):
    """
    Call this function anywhere in the app to log an analytics event.
    Example: track('match_generated', {'division': 'NCAA I', 'utr': 9.5})
    """
    try:
        uid = user_id
        if uid is None:
            try:
                uid = current_user.id if current_user.is_authenticated else None
            except Exception:
                uid = None

        event = AnalyticsEvent(
            user_id    = uid,
            event_type = event_type,
            event_data = json.dumps(data or {}),
        )
        db.session.add(event)
        db.session.commit()
    except Exception as e:
        # Never let analytics break the main app
        print(f'Analytics error: {e}')


# ── Admin Dashboard API ──
ADMIN_EMAILS = ['okyayd72@gmail.com']  # Add your email here

def is_admin():
    try:
        return current_user.is_authenticated and current_user.email in ADMIN_EMAILS
    except Exception:
        return False


@analytics_bp.get('/admin/api/stats')
@login_required
def admin_stats():
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403

    from backend.routes.athlete import AthleteProfile
    from backend.routes.auth import User

    # Total users
    total_users = User.query.count()

    # Completed profiles
    completed_profiles = AthleteProfile.query.filter_by(profile_complete=True).count()
    total_profiles = AthleteProfile.query.count()

    # Event counts
    def count_event(event_type):
        return AnalyticsEvent.query.filter_by(event_type=event_type).count()

    matches_generated  = count_event('match_generated')
    emails_generated   = count_event('email_generated')
    advisor_uses       = count_event('advisor_used')
    school_page_views  = count_event('school_page_viewed')

    # Most viewed schools (from match_generated events)
    school_counts = {}
    match_events = AnalyticsEvent.query.filter_by(event_type='match_generated').all()
    for e in match_events:
        try:
            data = json.loads(e.event_data or '{}')
            for school in data.get('schools', []):
                school_counts[school] = school_counts.get(school, 0) + 1
        except Exception:
            pass

    top_schools = sorted(school_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    # Recent signups (last 7 days)
    from datetime import timedelta
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_signups = User.query.filter(User.created_at >= week_ago).count() if hasattr(User, 'created_at') else 'N/A'

    # Daily activity (last 14 days)
    daily = {}
    for i in range(14):
        day = datetime.utcnow() - timedelta(days=i)
        day_str = day.strftime('%b %d')
        count = AnalyticsEvent.query.filter(
            AnalyticsEvent.created_at >= day.replace(hour=0, minute=0, second=0),
            AnalyticsEvent.created_at < day.replace(hour=23, minute=59, second=59)
        ).count()
        daily[day_str] = count

    return jsonify({
        'total_users':         total_users,
        'total_profiles':      total_profiles,
        'completed_profiles':  completed_profiles,
        'profile_completion_rate': round((completed_profiles / total_profiles * 100) if total_profiles else 0, 1),
        'matches_generated':   matches_generated,
        'emails_generated':    emails_generated,
        'advisor_uses':        advisor_uses,
        'school_page_views':   school_page_views,
        'recent_signups':      recent_signups,
        'top_schools':         [{'school': s, 'count': c} for s, c in top_schools],
        'daily_activity':      daily,
    })


@analytics_bp.get('/admin/api/users')
@login_required
def admin_users():
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403

    from backend.routes.auth import User
    from backend.routes.athlete import AthleteProfile

    users = User.query.order_by(User.created_at.desc()).limit(50).all() if hasattr(User, 'created_at') else User.query.limit(50).all()
    result = []
    for u in users:
        profile = AthleteProfile.query.filter_by(user_id=u.id).first()
        result.append({
            'id':       u.id,
            'name':     f"{u.first_name} {u.last_name}",
            'email':    u.email,
            'has_profile': profile is not None,
            'profile_complete': profile.profile_complete if profile else False,
            'utr':      profile.utr_rating if profile else None,
            'division': profile.division_preference if profile else None,
            'nationality': profile.nationality if profile else None,
        })

    return jsonify({'users': result})