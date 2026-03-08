from flask_login import UserMixin
from app import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)  # primary keys are required by SQLAlchemy
    email = db.Column(db.String(100))
    password = db.Column(db.String(256))  # Scrypt passwords are ~150 chars
    name = db.Column(db.String(1000))
    admin = db.Column(db.Boolean)
    is_global_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=False)
    account_owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    twofa_enabled = db.Column(db.Boolean, default=False, server_default=db.false(), nullable=False)
    twofa_secret = db.Column(db.String(500), nullable=True)   # Fernet-encrypted TOTP secret
    twofa_backup_codes = db.Column(db.Text, nullable=True)    # JSON array of scrypt-hashed backup codes

    # Relationships
    guests = db.relationship('User', backref=db.backref('account_owner', remote_side=[id]))

    # Constraints
    __table_args__ = (
        db.UniqueConstraint('email', name='uq_user_email'),
    )


class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Numeric(10, 2))
    frequency = db.Column(db.String(100))
    startdate = db.Column(db.Date)
    type = db.Column(db.String(100))
    firstdate = db.Column(db.Date)

    # Relationships
    user = db.relationship('User', backref='schedules')

    # Unique constraint per user
    __table_args__ = (db.UniqueConstraint('user_id', 'name', name='_user_schedule_uc'),)


class Scenario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Numeric(10, 2))
    frequency = db.Column(db.String(100))
    startdate = db.Column(db.Date)
    type = db.Column(db.String(100))
    firstdate = db.Column(db.Date)

    # Relationships
    user = db.relationship('User', backref='scenarios')

    # Unique constraint per user
    __table_args__ = (db.UniqueConstraint('user_id', 'name', name='_user_scenario_uc'),)


class Balance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2))
    date = db.Column(db.Date)

    # Relationships
    user = db.relationship('User', backref='balances')


class Hold(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2))
    name = db.Column(db.String(100))
    type = db.Column(db.String(100))

    # Relationships
    user = db.relationship('User', backref='holds')


class Skip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100))
    date = db.Column(db.Date)
    amount = db.Column(db.Numeric(10, 2))
    type = db.Column(db.String(100))

    # Relationships
    user = db.relationship('User', backref='skips')


class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    value = db.Column(db.Boolean)

    # Constraints
    __table_args__ = (
        db.UniqueConstraint('name', name='uq_settings_name'),
    )


class Email(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(500))
    server = db.Column(db.String(100))
    subjectstr = db.Column(db.String(100))
    startstr = db.Column(db.String(100))
    endstr = db.Column(db.String(100))
    # Expected sender address or domain for inbound balance emails.
    # Exact match: 'alerts@bank.com'  Domain match: '@bank.com'
    # NULL means no restriction is configured (ingestion proceeds with a warning).
    allowed_sender = db.Column(db.String(200), nullable=True)

    # Relationships
    user = db.relationship('User', backref='email_configs')


class GlobalEmailSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(500), nullable=False)
    smtp_server = db.Column(db.String(100), nullable=False)

    # Constraints - only one global email settings record allowed
    __table_args__ = (
        db.CheckConstraint('id = 1', name='single_row_check'),
    )


class AISettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    api_key = db.Column(db.String(500), nullable=True)  # Fernet-encrypted OpenAI API key
    model_version = db.Column(db.String(100), nullable=True)  # OpenAI model to use (e.g. gpt-4o-mini)
    last_updated = db.Column(db.DateTime, nullable=True)
    last_insights = db.Column(db.Text, nullable=True)  # JSON string of cached insights

    # Relationships
    user = db.relationship('User', backref='ai_settings')

    # One settings record per user
    __table_args__ = (
        db.UniqueConstraint('user_id', name='_ai_settings_user_uc'),
    )

