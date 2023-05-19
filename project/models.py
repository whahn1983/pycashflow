from flask_login import UserMixin
from . import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True) # primary keys are required by SQLAlchemy
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(1000))


class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    amount = db.Column(db.Numeric(10, 2))
    frequency = db.Column(db.String(100))
    startdate = db.Column(db.Date)

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
