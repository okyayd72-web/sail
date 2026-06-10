from flask import Blueprint, render_template
from flask_login import login_required

pages_bp = Blueprint('pages', __name__)

@pages_bp.get('/')
def index():
    return render_template('index.html')

@pages_bp.get('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@pages_bp.get('/advisor')
@login_required
def advisor():
    return render_template('advisor.html')

@pages_bp.get('/schools')
def schools():
    return render_template('schools.html')

@pages_bp.get('/pricing')
def pricing():
    return render_template('pricing.html')

@pages_bp.get('/admin')
@login_required
def admin_page():
    ADMIN_EMAILS = ['okyayd72@gmail.com']
    if current_user.email not in ADMIN_EMAILS:
        return redirect('/dashboard')
    return render_template('admin.html')