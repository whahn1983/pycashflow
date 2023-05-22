from flask import request, redirect, url_for, send_from_directory, flash
from flask_login import login_required, current_user
from flask import Blueprint, render_template
from .models import Schedule, Balance, Total, Running, User, Settings
from . import db
from datetime import datetime
import pandas as pd
import json
import plotly
import plotly.express as px
import os
from sqlalchemy import desc
from dateutil.relativedelta import relativedelta
from natsort import index_natsorted
import numpy as np
from werkzeug.security import generate_password_hash


main = Blueprint('main', __name__)


@main.route('/', methods=('GET', 'POST'))
@login_required
def index():
    balance = Balance.query.order_by(desc(Balance.date), desc(Balance.id)).first()

    months = 12
    weeks = 52
    years = 1
    quarters = 4
    biweeks = 26
    yearamount = request.form.get('yearamount')
    if yearamount == "1":
        months = 12
        weeks = 52
        years = 1
        quarters = 4
        biweeks = 26
    if yearamount == "2":
        months = 24
        weeks = 104
        years = 2
        quarters = 8
        biweeks = 52
    if yearamount == "3":
        months = 36
        weeks = 156
        years = 3
        quarters = 12
        biweeks = 78
    if yearamount == "4":
        months = 48
        weeks = 208
        years = 4
        quarters = 16
        biweeks = 104
    balance = Balance.query.order_by(desc(Balance.date)).first()
    db.session.query(Total).delete()
    db.session.query(Running).delete()
    db.session.commit()
    try:
        engine = db.create_engine(os.environ.get('DATABASE_URL')).connect()
    except:
        engine = db.create_engine('sqlite:///db.sqlite').connect()

    df = pd.read_sql('SELECT * FROM schedule;', engine)

    for i in range(len(df.index)):
        format = '%Y-%m-%d'
        startdate = df['startdate'][i]
        frequency = df['frequency'][i]
        amount = df['amount'][i]
        if frequency == 'Monthly':
            for k in range(months):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(months=k)
                total = Total(amount=amount, date=futuredate)
                db.session.add(total)
        elif frequency == 'Weekly':
            for k in range(weeks):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(weeks=k)
                total = Total(amount=amount, date=futuredate)
                db.session.add(total)
        elif frequency == 'Yearly':
            for k in range(years):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(years=k)
                total = Total(amount=amount, date=futuredate)
                db.session.add(total)
        elif frequency == 'Quarterly':
            for k in range(quarters):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(months=3 * k)
                total = Total(amount=amount, date=futuredate)
                db.session.add(total)
        elif frequency == 'BiWeekly':
            for k in range(biweeks):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(weeks=2 * k)
                total = Total(amount=amount, date=futuredate)
                db.session.add(total)
    db.session.commit()

    df = pd.read_sql('SELECT * FROM total;', engine)
    df = df.sort_values(by="date", key=lambda x: np.argsort(index_natsorted(df["date"])))

    runbalance = float(balance.amount)
    for i in df.iterrows():
        format = '%Y-%m-%d'
        rundate = i[1].date
        amount = i[1].amount
        runbalance += amount
        running = Running(amount=runbalance, date=datetime.strptime(rundate, format).date())
        db.session.add(running)
    db.session.commit()

    df = pd.read_sql('SELECT * FROM running;', engine)
    df = df.sort_values(by='date', ascending=True)
    fig = px.line(df, x="date", y="amount", template="plotly", title="Cash Flow")
    fig.update_xaxes(title_text='Date')
    fig.update_yaxes(title_text='Amount')
    fig.update_layout(paper_bgcolor="PaleTurquoise")

    graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    return render_template('index.html', title='Index', balance=balance.amount, graphJSON=graphJSON)


@main.route('/profile')
@login_required
def profile():

    return render_template('profile.html')


@main.route('/schedule')
@login_required
def schedule():
    schedule = Schedule.query

    return render_template('schedule_table.html', title='Schedule Table', schedule=schedule)


@main.route('/create', methods=('GET', 'POST'))
@login_required
def create():
    format = '%Y-%m-%d'
    if request.method == 'POST':
        name = request.form['name']
        amount = request.form['amount']
        frequency = request.form['frequency']
        startdate = request.form['startdate']
        schedule = Schedule(name=name,
                          amount=amount,
                          frequency=frequency,
                          startdate=datetime.strptime(startdate, format).date())
        db.session.add(schedule)
        db.session.commit()
        flash("Added Successfully")

        return redirect(url_for('main.schedule'))

    return redirect(url_for('main.schedule'))


@main.route('/update', methods=['GET', 'POST'])
@login_required
def update():
    format = '%Y-%m-%d'

    if request.method == 'POST':
        my_data = Schedule.query.get(request.form.get('id'))
        my_data.name = request.form['name']
        my_data.amount = request.form['amount']
        my_data.frequency = request.form['frequency']
        my_data.startdate = request.form['startdate']
        startdate = request.form['startdate']
        my_data.startdate = datetime.strptime(startdate, format).date()
        db.session.commit()
        flash("Updated Successfully")

        return redirect(url_for('main.schedule'))

    return redirect(url_for('main.schedule'))


@main.route('/delete/<id>')
@login_required
def schedule_delete(id):
    schedule = Schedule.query.filter_by(id=id).first()

    if schedule:
        db.session.delete(schedule)
        db.session.commit()
        flash("Deleted Successfully")

    return redirect(url_for('main.schedule'))


@main.route('/favicon')
def favicon():
    return send_from_directory(os.path.join(main.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')


@main.route('/balance', methods=('GET', 'POST'))
@login_required
def balance():
    format = '%Y-%m-%d'
    if request.method == 'POST':
        amount = request.form['amount']
        dateentry = request.form['date']
        balance = Balance(amount=amount,
                          date=datetime.strptime(dateentry, format).date())
        db.session.add(balance)
        db.session.commit()

        return redirect(url_for('main.index'))


@main.route('/changepw', methods=('GET', 'POST'))
@login_required
def changepw():
    if request.method == 'POST':
        curr_user = current_user.id
        my_user = User.query.filter_by(id=curr_user).first()
        password = request.form['password']
        my_user.password = generate_password_hash(password, method='scrypt')
        db.session.commit()

        return redirect(url_for('main.profile'))

    return redirect(url_for('main.profile'))


@main.route('/settings', methods=('GET', 'POST'))
@login_required
def settings():
    if request.method == 'POST':
        signupsettingname = Settings.query.filter_by(name='signup').first()

        if signupsettingname:
            signupvalue = request.form['signupvalue']
            print(signupvalue)
            print(eval(signupvalue))
            signupsettingname.value = eval(signupvalue)
            db.session.commit()

            return redirect(url_for('main.profile'))

        signupvalue = request.form['signupvalue']
        signupvalue = eval(signupvalue)
        settings = Settings(name="signup",
                          value=signupvalue)
        db.session.add(settings)
        db.session.commit()

        return redirect(url_for('main.profile'))

    return redirect(url_for('main.profile'))
