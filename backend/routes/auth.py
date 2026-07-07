from flask import Blueprint, request, jsonify, redirect, render_template, session
from flask_login import login_user, logout_user, login_required, current_user
from backend.app import db, limiter
from backend.models.user import User
import os
import secrets
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__)

BETA_CODE = os.getenv('BETA_CODE', 'SAIL50')


@auth_bp.post('/api/auth/register')
@limiter.limit("5 per minute")
def register():
    data = request.get_json()

    if not data or not all(k in data for k in ['email', 'password', 'first_name', 'last_name']):
        return jsonify({'error': 'All fields are required.'}), 400

    if len(data['password']) < 8:
        return jsonify({'error': 'Password must be at least 8 characters.'}), 400
        # Age confirmation (13+ / parental permission) — required to register
    if not data.get('age_confirm'):
        return jsonify({'error': 'You must confirm you are 13 or older to create an account.'}), 400

    submitted_code = data.get('beta_code', '').strip().upper()
    if submitted_code != BETA_CODE.upper():
        return jsonify({'error': 'Invalid beta access code. Please check your invite email.'}), 403

    user_count = User.query.count()
    if user_count >= 50:
        return jsonify({'error': 'Beta is currently full. Check back soon!'}), 403

    if User.query.filter_by(email=data['email'].lower()).first():
        return jsonify({'error': 'An account with this email already exists.'}), 409

    user = User(
        email      = data['email'].lower().strip(),
        first_name = data['first_name'].strip(),
        last_name  = data['last_name'].strip(),
        role       = data.get('role', 'athlete')
    )
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()

    try:
        from backend.routes.analytics import track
        track('user_registered', {
            'role': data.get('role', 'athlete'),
            'beta_code': submitted_code,
        }, user_id=user.id)
    except Exception:
        pass

    session.permanent = True
    login_user(user)
    return jsonify({'message': 'Account created!', 'user': user.to_dict()}), 201


@auth_bp.post('/api/auth/login')
@limiter.limit("5 per minute")
def login():
    data = request.get_json()

    if not data or not all(k in data for k in ['email', 'password']):
        return jsonify({'error': 'Email and password are required.'}), 400

    user = User.query.filter_by(email=data['email'].lower()).first()

    if not user or not user.check_password(data['password']):
        return jsonify({'error': 'Invalid email or password.'}), 401

    session.permanent = True
    login_user(user)
    return jsonify({'message': 'Logged in!', 'user': user.to_dict()}), 200


@auth_bp.post('/api/auth/logout')
@login_required
def logout():
    logout_user()
    return jsonify({'message': 'Logged out.'}), 200


@auth_bp.get('/api/auth/me')
def me():
    if current_user.is_authenticated:
        return jsonify({'user': current_user.to_dict()}), 200
    return jsonify({'user': None}), 200


@auth_bp.post('/api/auth/forgot-password')
@limiter.limit("3 per hour")
def forgot_password():
    data = request.get_json()
    email = data.get('email', '').lower().strip()

    user = User.query.filter_by(email=email).first()

    if user:
        token = secrets.token_urlsafe(32)
        user.reset_token        = token
        user.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()

        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail

            reset_url = f"https://sailscholarship.com/reset-password?token={token}"
            sg        = sendgrid.SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
            message   = Mail(
                from_email  = 'noreply@sailscholarship.com',
                to_emails   = email,
                subject     = 'Reset your SAIL password',
                html_content = f'''
                <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:2rem;background:#050d1a;color:#f0eee8;border-radius:16px;">
                  <h2 style="color:#00c9a7;margin-bottom:1rem;">Reset your password</h2>
                  <p style="color:#8fa0b8;line-height:1.7;margin-bottom:1.5rem;">
                    Click the button below to reset your SAIL password. This link expires in <strong style="color:#f0eee8;">1 hour</strong>.
                  </p>
                  <a href="{reset_url}" style="display:inline-block;background:#00c9a7;color:#050d1a;padding:.85rem 2rem;border-radius:10px;font-weight:700;text-decoration:none;font-size:1rem;">
                    Reset Password →
                  </a>
                  <p style="color:#4d6278;font-size:.8rem;margin-top:1.5rem;">
                    If you didn't request this, you can safely ignore this email.
                  </p>
                </div>
                '''
            )
            sg.send(message)
        except Exception as e:
            print(f"Email error: {e}")

    return jsonify({'message': 'If that email exists you will receive a reset link shortly.'}), 200


@auth_bp.post('/api/auth/reset-password')
@limiter.limit("5 per minute")
def reset_password():
    data        = request.get_json()
    token       = data.get('token', '').strip()
    new_password = data.get('password', '').strip()

    if not token or not new_password:
        return jsonify({'error': 'Token and new password are required.'}), 400

    if len(new_password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters.'}), 400

    user = User.query.filter_by(reset_token=token).first()

    if not user or not user.reset_token_expiry:
        return jsonify({'error': 'Invalid or expired reset link.'}), 400

    if datetime.utcnow() > user.reset_token_expiry:
        return jsonify({'error': 'This reset link has expired. Please request a new one.'}), 400

    user.set_password(new_password)
    user.reset_token        = None
    user.reset_token_expiry = None
    db.session.commit()

    return jsonify({'message': 'Password reset successfully! You can now log in.'}), 200


@auth_bp.get('/login')
def login_page():
    return render_template('login.html')


@auth_bp.get('/register')
def register_page():
    return render_template('register.html')


@auth_bp.get('/reset-password')
def reset_password_page():
    return render_template('reset_password.html')


@auth_bp.get('/logout')
@login_required
def logout_page():
    logout_user()
    return redirect('/')