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
                               error=None, form={})

    # ── POST: validate and create ──
    form = request.form
    school_name    = form.get('school_name', '').strip()
    division       = form.get('division', '').strip()
    position_label = form.get('position_label', '').strip()
    recruit_type   = form.get('recruit_type', '').strip()
    gender         = form.get('gender', '').strip()
    description    = form.get('description', '').strip()
    raw_year       = form.get('target_grad_year', '').strip()

    error = None
    utr_min = utr_max = None
    try:
        utr_min = float(form.get('utr_min', ''))
        utr_max = float(form.get('utr_max', ''))
    except (ValueError, TypeError):
        error = 'UTR values must be numbers.'

    if not error:
        if not school_name:
            error = 'School name is required.'
        elif division not in DIVISIONS:
            error = 'Select a valid division.'
        elif not position_label:
            error = 'Position label is required (e.g. "Lineup #3-4").'
        elif recruit_type not in ('transfer', 'newcomer', 'either'):
            error = 'Select a valid recruit type.'
        elif gender not in ('male', 'female'):
            error = 'Select a gender.'
        elif utr_max < utr_min:
            error = 'UTR max must be ≥ UTR min.'

    if error:
        return render_template('coach_posting_new.html', divisions=DIVISIONS,
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
    # Verification gate: unverified coaches see count only, no PII
    verified = bool(current_user.is_verified_coach)
    return render_template('coach_applicants.html', posting=posting,
                           applications=apps, verified=verified)


# ─── STUDENT ROUTES ───────────────────────────────────────────────────────────

@coach_bp.get('/opportunities')
@login_required
def opportunities():
    division     = request.args.get('division', '').strip()
    recruit_type = request.args.get('recruit_type', '').strip()
    gender       = request.args.get('gender', '').strip()
    utr_str      = request.args.get('utr', '').strip()

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
        filters={
            'division':     division,
            'recruit_type': recruit_type,
            'gender':       gender,
            'utr':          utr_str,
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
