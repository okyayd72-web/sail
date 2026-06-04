import uuid
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from backend.app import db, login_manager

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id            = db.Column(db.String(36), primary_key=True,
                               default=lambda: str(uuid.uuid4()))
    email         = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name    = db.Column(db.String(100), nullable=False)
    last_name     = db.Column(db.String(100), nullable=False)
    role          = db.Column(db.String(20), default='athlete')
    is_verified   = db.Column(db.Boolean, default=True)
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def to_dict(self):
        return {
            'id':         self.id,
            'email':      self.email,
            'first_name': self.first_name,
            'last_name':  self.last_name,
            'full_name':  self.full_name,
            'role':       self.role,
        }

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)