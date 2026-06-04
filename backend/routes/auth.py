from flask import Blueprint, request, jsonify, redirect, url_for, render_template
from flask_login import login_user, logout_user, login_required, current_user
from backend.app import db
from backend.models.user import User

auth_bp = Blueprint('auth', __name__)

@auth_bp.post('/api/auth/register')
def register():
    data = request.get_json()

    if not data or not all(k in data for k in ['email','password','first_name','last_name']):
        return jsonify({'error': 'All fields are required.'}), 400

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

    login_user(user, remember=True)
    return jsonify({'message': 'Account created!', 'user': user.to_dict()}), 201

@auth_bp.post('/api/auth/login')
def login():
    data = request.get_json()

    if not data or not all(k in data for k in ['email','password']):
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