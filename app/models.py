from flask_login import UserMixin
from app import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)  # primary keys are required by SQLAlchemy
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(1000))


class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True)
    amount = db.Column(db.Numeric(10, 2))
    frequency = db.Column(db.String(100))
    startdate = db.Column(db.Date)
    type = db.Column(db.String(100))

    def to_dict(self):
        return {
            'name': self.name,
            'amount': self.amount,
            'frequency': self.frequency,
            'startdate': self.startdate,
        }


class Balance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Numeric(10, 2))
    date = db.Column(db.Date)


class Total(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Numeric(10, 2))
    date = db.Column(db.Date)
    name = db.Column(db.String(100))
    type = db.Column(db.String(100))


class Hold(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Numeric(10, 2))
    name = db.Column(db.String(100))
    type = db.Column(db.String(100))


class Skip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    date = db.Column(db.Date)
    amount = db.Column(db.Numeric(10, 2))
    type = db.Column(db.String(100))


class Running(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Numeric(10, 2))
    date = db.Column(db.Date)


class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True)
    value = db.Column(db.Boolean)


class Transactions(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    date = db.Column(db.Date)
    amount = db.Column(db.Numeric(10, 2))
    type = db.Column(db.String(100))


class Email(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    server = db.Column(db.String(100))
    subjectstr = db.Column(db.String(100))
    startstr = db.Column(db.String(100))
    endstr = db.Column(db.String(100))
