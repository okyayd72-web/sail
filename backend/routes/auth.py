from flask import Blueprint, request, jsonify, redirect, render_template
from flask_login import login_user, logout_user, login_required, current_user
from backend.app import db
from backend.models.user import User
import os

auth_bp = Blueprint('auth', __name__)

# ── Beta access code ──
BETA_CODE = os.getenv('BETA_CODE', 'SAIL50')


@auth_bp.post('/api/auth/register')
def register():
    data = request.get_json()

    if not data or not all(k in data for k in ['email', 'password', 'first_name', 'last_name']):
        return jsonify({'error': 'All fields are required.'}), 400

    # ── Validate beta code ──
    submitted_code = data.get('beta_code', '').strip().upper()
    if submitted_code != BETA_CODE.upper():
        return jsonify({'error': 'Invalid beta access code. Please check your invite email.'}), 403
    
  # ── Beta user cap ──  ← ADD THIS HERE
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

    # ── Analytics ──
    try:
        from backend.routes.analytics import track
        track('user_registered', {
            'role': data.get('role', 'athlete'),
            'beta_code': submitted_code,
        }, user_id=user.id)
    except Exception:
        pass

    login_user(user, remember=True)
    return jsonify({'message': 'Account created!', 'user': user.to_dict()}), 201


@auth_bp.post('/api/auth/login')
def login():
    data = request.get_json()

    if not data or not all(k in data for k in ['email', 'password']):
        return jsonify({'error': 'Email and password are required.'}), 400

    user = User.query.filter_by(email=data['email'].lower()).first()

    if not user or not user.check_password(data['password']):
        return jsonify({'error': 'Invalid email or password.'}), 401

    login_user(user, remember=True)
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


@auth_bp.get('/login')
def login_page():
    return render_template('login.html')


@auth_bp.get('/register')
def register_page():
    return render_template('register.html')


@auth_bp.get('/logout')
@login_required
def logout_page():
    logout_user()
    return redirect('/')