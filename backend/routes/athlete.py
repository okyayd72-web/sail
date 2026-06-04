from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from backend.app import db

athlete_bp = Blueprint('athlete', __name__)

class AthleteProfile(db.Model):
    __tablename__ = 'athlete_profiles'
    import uuid
    id                  = db.Column(db.String(36), primary_key=True, default=lambda: str(__import__('uuid').uuid4()))
    user_id             = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, unique=True)
    sport               = db.Column(db.String(100))
    position            = db.Column(db.String(100))
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
                  self.division_preference, self.gpa, self.nationality]
        filled = sum(1 for f in fields if f)
        return int((filled / len(fields)) * 100)

    def to_dict(self):
        return {
            'id': self.id, 'sport': self.sport, 'position': self.position,
            'graduation_year': self.graduation_year, 'athletic_level': self.athletic_level,
            'division_preference': self.division_preference, 'gpa': self.gpa,
            'sat_score': self.sat_score, 'act_score': self.act_score,
            'nationality': self.nationality, 'state_province': self.state_province,
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
    required = ['sport','graduation_year','gpa','nationality','athletic_level','division_preference']
    p.profile_complete = all(getattr(p, f) for f in required)
    db.session.commit()
    return jsonify({'profile': p.to_dict()})

@athlete_bp.get('/api/athlete/matches')
@login_required
def get_matches():
    return jsonify({'matches': []})

@athlete_bp.post('/api/athlete/matches/refresh')
@login_required
def refresh_matches():
    p = AthleteProfile.query.filter_by(user_id=current_user.id).first()
    if not p or not p.profile_complete:
        return jsonify({'error': 'Please complete your profile first.'}), 400
    return jsonify({'matches': [], 'message': 'Connect your API key to get AI matches.'})