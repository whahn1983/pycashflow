from flask_login import UserMixin
from app import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)  # primary keys are required by SQLAlchemy
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(1000))
    admin = db.Column(db.Boolean)
    is_global_admin = db.Column(db.Boolean, default=False)
    account_owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    # Relationships
    guests = db.relationship('User', backref=db.backref('account_owner', remote_side=[id]))


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
    name = db.Column(db.String(100), unique=True)
    value = db.Column(db.Boolean)


class Email(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(100))
    server = db.Column(db.String(100))
    subjectstr = db.Column(db.String(100))
    startstr = db.Column(db.String(100))
    endstr = db.Column(db.String(100))

    # Relationships
    user = db.relationship('User', backref='email_configs')

