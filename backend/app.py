import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__,
                template_folder='../frontend/pages',
                static_folder='../frontend/static')

    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'sail-dev-secret-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///sail.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Secure session cookies
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE']   = os.getenv('FLASK_ENV') == 'production'

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login_page'

    from backend.routes.auth          import auth_bp
    from backend.routes.pages         import pages_bp
    from backend.routes.athlete       import athlete_bp
    from backend.routes.ai_routes     import ai_bp
    from backend.routes.tennis_routes import tennis_bp
    from backend.routes.analytics     import analytics_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(athlete_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(tennis_bp)
    app.register_blueprint(analytics_bp)

    with app.app_context():
        db.drop_all()
        db.create_all()

    return app