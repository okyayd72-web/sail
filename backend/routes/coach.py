import logging
import os
import secrets
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, render_template, redirect
from flask_login import login_required, current_user
from backend.app import db, limiter
from backend.models.user import User

coach_bp = Blueprint('coach', __name__)

DIVISIONS = ['NCAA I', 'NCAA II', 'NCAA III', 'NAIA', 'JUCO', 'CCCAA', 'USCAA', 'NWAC', 'NCCAA']

RECRUITING_TERMS = [
    'Fall 2026', 'Spring 2027',
    'Fall 2027', 'Spring 2028',
    'Fall 2028', 'Spring 2029',
    '2026-27',   '2027-28',    '2028-29',
]


# ─── MODELS ──────────────────────────────────────────────────────────────────

class CoachPosting(db.Model):
    __tablename__ = 'coach_postings'

    id               = db.Column(db.Integer,     primary_key=True)
    coach_user_id    = db.Column(db.String(36),  db.ForeignKey('users.id'), nullable=False)
    school_name      = db.Column(db.String(200),  nullable=False)
    division         = db.Column(db.String(50),   nullable=False)
    position_label   = db.Column(db.String(100),  nullable=False)
    utr_min          = db.Column(db.Float,         nullable=False)
    utr_max          = db.Column(db.Float,         nullable=False)
    recruit_type     = db.Column(db.String(20),   nullable=False)   # transfer / newcomer / either
    target_grad_year = db.Column(db.Integer,       nullable=True)
    gender           = db.Column(db.String(10),   nullable=False)   # male / female
    description      = db.Column(db.Text,          nullable=True)
    recruiting_term  = db.Column(db.String(50),    nullable=False, server_default='TBD')
    is_active        = db.Column(db.Boolean,       default=True, nullable=False)
    created_at       = db.Column(db.DateTime,      default=datetime.utcnow)

    coach        = db.relationship('User', foreign_keys=[coach_user_id])
    applications = db.relationship('PostingApplication', backref='posting',
                                   lazy='dynamic', cascade='all, delete-orphan')


class PostingApplication(db.Model):
    __tablename__ = 'posting_applications'
    __table_args__ = (
        db.UniqueConstraint('posting_id', 'student_user_id', name='uq_posting_student'),
    )

    id              = db.Column(db.Integer,    primary_key=True)
    posting_id      = db.Column(db.Integer,    db.ForeignKey('coach_postings.id'), nullable=False)
    student_user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    message         = db.Column(db.Text,       nullable=True)
    status          = db.Column(db.String(20), default='submitted', nullable=False)
    created_at      = db.Column(db.DateTime,   default=datetime.utcnow)

    student = db.relationship('User', foreign_keys=[student_user_id])


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _gate_coach():
    """Returns a redirect if current_user is not a coach, else None."""
    if current_user.role != 'coach':
        return redirect('/dashboard')
    return None


# ─── COACH ROUTES ─────────────────────────────────────────────────────────────

@coach_bp.get('/coach/postings')
@login_required
def coach_postings():
    gate = _gate_coach()
    if gate:
        return gate
    postings = (CoachPosting.query
                .filter_by(coach_user_id=current_user.id)
                .order_by(CoachPosting.created_at.desc())
                .all())
    # Attach count as a plain attribute so template doesn't need .count()
    for p in postings:
        p._applicant_count = p.applications.count()
    return render_template('coach_postings.html', postings=postings)


@coach_bp.route('/coach/postings/new', methods=['GET', 'POST'])
@login_required
def coach_posting_new():
    gate = _gate_coach()
    if gate:
        return gate

    if request.method == 'GET':
        return render_template('coach_posting_new.html', divisions=DIVISIONS,
                               recruiting_terms=RECRUITING_TERMS,
                               coach_school=current_user.coach_school,
                               error=None, form={})

    # ── POST: validate and create ──
    # School is always taken from the coach's account — never from the form.
    if not current_user.coach_school:
        return render_template('coach_posting_new.html', divisions=DIVISIONS,
                               recruiting_terms=RECRUITING_TERMS,
                               coach_school=None,
                               error=None, form=request.form)

    school_name      = current_user.coach_school          # server-set; form value ignored
    form = request.form
    division         = form.get('division', '').strip()
    position_label   = form.get('position_label', '').strip()
    recruit_type     = form.get('recruit_type', '').strip()
    gender           = form.get('gender', '').strip()
    description      = form.get('description', '').strip()
    raw_year         = form.get('target_grad_year', '').strip()
    recruiting_term  = form.get('recruiting_term', '').strip()

    error = None
    utr_min = utr_max = None
    try:
        utr_min = float(form.get('utr_min', ''))
        utr_max = float(form.get('utr_max', ''))
    except (ValueError, TypeError):
        error = 'UTR values must be numbers.'

    if not error:
        if division not in DIVISIONS:
            error = 'Select a valid division.'
        elif not position_label:
            error = 'Position label is required (e.g. "Lineup #3-4").'
        elif recruit_type not in ('transfer', 'newcomer', 'either'):
            error = 'Select a valid recruit type.'
        elif gender not in ('male', 'female'):
            error = 'Select a gender.'
        elif utr_max < utr_min:
            error = 'UTR max must be ≥ UTR min.'
        elif recruiting_term not in RECRUITING_TERMS:
            error = 'Select a valid recruiting term.'

    if error:
        return render_template('coach_posting_new.html', divisions=DIVISIONS,
                               recruiting_terms=RECRUITING_TERMS,
                               coach_school=current_user.coach_school,
                               error=error, form=form)

    target_grad_year = int(raw_year) if raw_year.isdigit() else None

    posting = CoachPosting(
        coach_user_id    = current_user.id,
        school_name      = school_name,
        division         = division,
        position_label   = position_label,
        utr_min          = utr_min,
        utr_max          = utr_max,
        recruit_type     = recruit_type,
        target_grad_year = target_grad_year,
        gender           = gender,
        description      = description or None,
        recruiting_term  = recruiting_term,
    )
    db.session.add(posting)
    db.session.commit()
    return redirect('/coach/postings')


@coach_bp.post('/coach/postings/<int:posting_id>/toggle')
@login_required
def toggle_posting(posting_id):
    if current_user.role != 'coach':
        return jsonify({'error': 'Forbidden'}), 403
    posting = CoachPosting.query.get_or_404(posting_id)
    if posting.coach_user_id != current_user.id:         # IDOR guard
        return jsonify({'error': 'Forbidden'}), 403
    posting.is_active = not posting.is_active
    db.session.commit()
    return jsonify({'is_active': posting.is_active})


@coach_bp.get('/coach/postings/<int:posting_id>/applicants')
@login_required
def coach_applicants(posting_id):
    gate = _gate_coach()
    if gate:
        return gate
    posting = CoachPosting.query.get_or_404(posting_id)
    if posting.coach_user_id != current_user.id:         # IDOR guard
        return redirect('/coach/postings')
    apps = (PostingApplication.query
            .filter_by(posting_id=posting_id)
            .order_by(PostingApplication.created_at.desc())
            .all())
    # Manual-approval gate: only manually approved coaches may see student PII.
    # Email verification (is_verified_coach) alone is not sufficient.
    verified = bool(current_user.coach_manually_approved)

    # Fetch athlete profiles only for verified coaches, only for applicants to THIS posting.
    # Withheld pre-contact (minor PII): nationality, location, video — pending privacy-counsel review before any broader exposure.
    profiles = {}
    if verified:
        from backend.routes.athlete import AthleteProfile
        for app in apps:
            p = AthleteProfile.query.filter_by(user_id=app.student_user_id).first()
            if p:
                profiles[app.student_user_id] = {
                    'gender':                  p.gender,
                    'utr_rating':              p.utr_rating,
                    'intended_major':          p.intended_major,
                    'athletic_level':          p.athletic_level,
                    'gpa':                     p.gpa,
                    'graduation_year':         p.graduation_year,
                    'sat_score':               p.sat_score,
                    'act_score':               p.act_score,
                    'division_preference':     p.division_preference,
                    'school_size_preference':  p.school_size_preference,
                    'itf_junior_rank_singles': p.itf_junior_rank_singles,
                    'itf_junior_rank_doubles': p.itf_junior_rank_doubles,
                    'itf_junior_titles':       p.itf_junior_titles,
                    'atp_wta_rank_singles':    p.atp_wta_rank_singles,
                    'atp_wta_rank_doubles':    p.atp_wta_rank_doubles,
                    'total_titles':            p.total_titles,
                    'best_wins':               p.best_wins,
                    'national_achievements':   p.national_achievements,
                }

    return render_template('coach_applicants.html', posting=posting,
                           applications=apps, verified=verified, profiles=profiles)


# ─── STUDENT ROUTES ───────────────────────────────────────────────────────────

@coach_bp.get('/opportunities')
@login_required
def opportunities():
    if current_user.role == 'coach':
        return redirect('/coach/postings')

    division         = request.args.get('division', '').strip()
    recruit_type     = request.args.get('recruit_type', '').strip()
    gender           = request.args.get('gender', '').strip()
    utr_str          = request.args.get('utr', '').strip()
    term_filter      = request.args.get('term', '').strip()

    q = CoachPosting.query.filter_by(is_active=True)
    if division:
        q = q.filter(CoachPosting.division == division)
    if recruit_type:
        q = q.filter(CoachPosting.recruit_type == recruit_type)
    if gender:
        q = q.filter(CoachPosting.gender == gender)
    if utr_str:
        try:
            utr = float(utr_str)
            q = q.filter(CoachPosting.utr_min <= utr, CoachPosting.utr_max >= utr)
        except ValueError:
            pass
    if term_filter:
        q = q.filter(CoachPosting.recruiting_term == term_filter)

    postings = q.order_by(CoachPosting.created_at.desc()).all()

    applied_ids = set()
    if current_user.role == 'athlete':
        applied_ids = {
            a.posting_id
            for a in PostingApplication.query
                                       .filter_by(student_user_id=current_user.id)
                                       .all()
        }

    return render_template(
        'opportunities.html',
        postings=postings,
        applied_ids=applied_ids,
        divisions=DIVISIONS,
        recruiting_terms=RECRUITING_TERMS,
        filters={
            'division':     division,
            'recruit_type': recruit_type,
            'gender':       gender,
            'utr':          utr_str,
            'term':         term_filter,
        },
    )


@coach_bp.post('/opportunities/<int:posting_id>/apply')
@login_required
def apply_to_posting(posting_id):
    if current_user.role != 'athlete':
        return jsonify({'error': 'Only student accounts can apply.'}), 403

    posting = CoachPosting.query.get_or_404(posting_id)
    if not posting.is_active:
        return jsonify({'error': 'This posting is no longer active.'}), 400

    # Python-level duplicate check before hitting the DB unique constraint
    existing = PostingApplication.query.filter_by(
        posting_id=posting_id, student_user_id=current_user.id
    ).first()
    if existing:
        return jsonify({'error': 'You have already applied to this posting.'}), 409

    data        = request.get_json() or {}
    raw_message = (data.get('message') or '').strip()
    application = PostingApplication(
        posting_id      = posting_id,
        student_user_id = current_user.id,
        message         = raw_message or None,
    )
    try:
        db.session.add(application)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Could not submit application. Please try again.'}), 500

    # Notify the coach — no student PII; failure must not affect the application record
    try:
        coach_user = User.query.get(posting.coach_user_id)
        if coach_user and coach_user.email:
            _notify_coach_new_applicant(coach_user.email, posting)
    except Exception:
        pass

    return jsonify({'success': True}), 201


@coach_bp.get('/my-applications')
@login_required
def my_applications():
    if current_user.role != 'athlete':
        return redirect('/dashboard')
    apps = (PostingApplication.query
            .filter_by(student_user_id=current_user.id)
            .order_by(PostingApplication.created_at.desc())
            .all())
    return render_template('my_applications.html', applications=apps)


# ─── COACH VERIFICATION ───────────────────────────────────────────────────────

def _send_coach_verification_email(to_email, token):
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail
        verify_url = f"https://sailscholarship.com/coach/verify/{token}"
        sg = sendgrid.SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
        message = Mail(
            from_email='noreply@sailscholarship.com',
            to_emails=to_email,
            subject='Verify your SAIL coach account',
            html_content=f'''
            <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:2rem;background:#050d1a;color:#f0eee8;border-radius:16px;">
              <h2 style="color:#00c9a7;margin-bottom:1rem;">Verify your coach account</h2>
              <p style="color:#8fa0b8;line-height:1.7;margin-bottom:1.5rem;">
                Click the button below to verify your SAIL coach account and access student applicants.
                This link expires in <strong style="color:#f0eee8;">24 hours</strong>.
              </p>
              <a href="{verify_url}" style="display:inline-block;background:#00c9a7;color:#050d1a;padding:.85rem 2rem;border-radius:10px;font-weight:700;text-decoration:none;font-size:1rem;">
                Verify Account →
              </a>
              <p style="color:#4d6278;font-size:.8rem;margin-top:1.5rem;">
                If you didn't create a SAIL coach account, you can safely ignore this email.
              </p>
            </div>
            '''
        )
        sg.send(message)
    except Exception as e:
        logging.error(f"Coach verification email error: {e}")


def _notify_coach_new_applicant(to_email, posting):
    """Email the posting's coach that a new application arrived. Contains NO student PII."""
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail
        applicants_url = (
            f"https://sailscholarship.com/coach/postings/{posting.id}/applicants"
        )
        term_str = (
            f" ({posting.recruiting_term})"
            if posting.recruiting_term and posting.recruiting_term != 'TBD'
            else ''
        )
        sg = sendgrid.SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
        message = Mail(
            from_email='noreply@sailscholarship.com',
            to_emails=to_email,
            subject='New applicant for your SAIL posting',
            html_content=f'''
            <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:2rem;background:#050d1a;color:#f0eee8;border-radius:16px;">
              <h2 style="color:#00c9a7;margin-bottom:1rem;">New applicant 🎾</h2>
              <p style="color:#8fa0b8;line-height:1.7;margin-bottom:1.5rem;">
                You have a new applicant for
                <strong style="color:#f0eee8;">{posting.position_label}{term_str}</strong>
                at <strong style="color:#f0eee8;">{posting.school_name}</strong>.
              </p>
              <a href="{applicants_url}" style="display:inline-block;background:#00c9a7;color:#050d1a;padding:.85rem 2rem;border-radius:10px;font-weight:700;text-decoration:none;font-size:1rem;">
                View Applicants →
              </a>
              <p style="color:#4d6278;font-size:.8rem;margin-top:1.5rem;">
                Student details are available after logging in, subject to your approval status.
                No student information is included in this email.
              </p>
            </div>
            '''
        )
        sg.send(message)
    except Exception as e:
        logging.error(f"Coach applicant notification error: {e}")


@coach_bp.get('/coach/verify/<token>')
def verify_coach_email(token):
    user = User.query.filter_by(coach_verification_token=token).first()
    if not user or not user.coach_verification_sent_at:
        return render_template('coach_verify_error.html')
    if datetime.utcnow() > user.coach_verification_sent_at + timedelta(hours=24):
        return render_template('coach_verify_error.html')
    user.is_verified_coach          = True
    user.coach_verification_token   = None
    user.coach_verification_sent_at = None
    db.session.commit()
    return render_template('coach_verify_success.html')


@coach_bp.post('/coach/resend-verification')
@login_required
@limiter.limit("3 per hour")
def resend_verification():
    if current_user.role != 'coach':
        return jsonify({'error': 'Not a coach account.'}), 403
    if current_user.is_verified_coach:
        return jsonify({'error': 'Already verified.'}), 400
    token = secrets.token_urlsafe(32)
    current_user.coach_verification_token   = token
    current_user.coach_verification_sent_at = datetime.utcnow()
    db.session.commit()
    _send_coach_verification_email(current_user.email, token)
    return jsonify({'message': 'Verification email sent.'}), 200
