from flask import request, redirect, url_for, send_from_directory, flash
from flask_login import login_required, current_user
from flask import Blueprint, render_template
from .models import Schedule, Balance, Total, Running, User, Settings, Transactions, Email
from project import db
from datetime import datetime
import pandas as pd
import json
import plotly
import plotly.express as px
import os
from sqlalchemy import desc, func
from dateutil.relativedelta import relativedelta
from natsort import index_natsorted
import numpy as np
from werkzeug.security import generate_password_hash
import decimal
import plotly.graph_objs as go


main = Blueprint('main', __name__)


@main.route('/', methods=('GET', 'POST'))
@login_required
def index():
    # query the latest balance information
    balance = Balance.query.order_by(desc(Balance.date), desc(Balance.id)).first()

    try:
        balance.amount
        if balance.amount:
            db.session.query(Balance).delete()
            balance = Balance(amount=balance.amount, date=datetime.today())
            db.session.add(balance)
            db.session.commit()
    except:
        balance = Balance(amount='0',
                          date=datetime.today())
        db.session.add(balance)
        db.session.commit()

    # retrieve the number of years for the cash flow plot
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

    # empty the tables to create fresh data from the schedule
    db.session.query(Total).delete()
    db.session.query(Running).delete()
    db.session.query(Transactions).delete()
    db.session.commit()
    try:
        engine = db.create_engine(os.environ.get('DATABASE_URL')).connect()
    except:
        engine = db.create_engine('sqlite:///db.sqlite').connect()

    # pull the schedule information
    df = pd.read_sql('SELECT * FROM schedule;', engine)

    # loop through the schedule and create transactions in a table out to the future number of years
    for i in range(len(df.index)):
        format = '%Y-%m-%d'
        name = df['name'][i]
        startdate = df['startdate'][i]
        frequency = df['frequency'][i]
        amount = df['amount'][i]
        type = df['type'][i]
        if frequency == 'Monthly':
            for k in range(months):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(months=k)
                if type == 'Income':
                    rollbackdate = datetime.combine(futuredate, datetime.min.time())
                    total = Total(type=type, name=name, amount=amount, date=pd.tseries.offsets.BDay(1).rollback(rollbackdate).date())
                else:
                    total = Total(type=type, name=name, amount=amount, date=futuredate - pd.tseries.offsets.BDay(0))
                db.session.add(total)
        elif frequency == 'Weekly':
            for k in range(weeks):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(weeks=k)
                total = Total(type=type, name=name, amount=amount, date=futuredate - pd.tseries.offsets.BDay(0))
                db.session.add(total)
        elif frequency == 'Yearly':
            for k in range(years):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(years=k)
                total = Total(type=type, name=name, amount=amount, date=futuredate - pd.tseries.offsets.BDay(0))
                db.session.add(total)
        elif frequency == 'Quarterly':
            for k in range(quarters):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(months=3 * k)
                total = Total(type=type, name=name, amount=amount, date=futuredate - pd.tseries.offsets.BDay(0))
                db.session.add(total)
        elif frequency == 'BiWeekly':
            for k in range(biweeks):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(weeks=2 * k)
                total = Total(type=type, name=name, amount=amount, date=futuredate - pd.tseries.offsets.BDay(0))
                db.session.add(total)
        elif frequency == 'Onetime':
            futuredate = datetime.strptime(startdate, format).date()
            if futuredate < datetime.today().date():
                onetimeschedule = Schedule.query.filter_by(name=name).first()
                db.session.delete(onetimeschedule)
            else:
                total = Total(type=type, name=name, amount=amount, date=futuredate)
                db.session.add(total)
    db.session.commit()

    # retrieve the total future transactions
    df = pd.read_sql('SELECT * FROM total;', engine)
    df = df.sort_values(by="date", key=lambda x: np.argsort(index_natsorted(df["date"])))

    # collect the next 60 days of transactions for the transactions table
    format = '%Y-%m-%d'
    for i in df.iterrows():
        if datetime.today().date() + relativedelta(months=1) > \
                datetime.strptime(i[1].date, format).date() > datetime.today().date():
            transactions = Transactions(name=i[1].iloc[3], type=i[1].type, amount=i[1].amount, date=datetime.strptime(i[1].date, format).date())
            db.session.add(transactions)
    db.session.commit()

    # for schedules marked as expenses, make the value negative for the sum
    for i in df.iterrows():
        id = i[1].id
        amount = i[1].amount
        type = i[1].type
        if type == 'Expense':
            amount = float(amount) * -1
            df.at[id - 1, 'amount'] = amount
        elif type == 'Income':
            pass

    # group total transactions by date and sum the amounts for each date
    df = df.groupby("date")['amount'].sum().reset_index()

    # loop through the total transactions by date and add the sums to the total balance amount
    runbalance = float(balance.amount)
    running = Running(amount=runbalance, date=datetime.today().date())
    db.session.add(running)
    for i in df.iterrows():
        format = '%Y-%m-%d'
        rundate = i[1].date
        amount = i[1].amount
        if datetime.strptime(rundate, format).date() > datetime.today().date():
            runbalance += amount
            running = Running(amount=runbalance, date=datetime.strptime(rundate, format).date())
            db.session.add(running)
    db.session.commit()

    # plot the running balances by date on a line plot
    df = pd.read_sql('SELECT * FROM running;', engine)
    df = df.sort_values(by='date', ascending=False)
    minbalance = df['amount'].min()
    minbalance = decimal.Decimal(str(minbalance)).quantize(decimal.Decimal('.01'))
    if minbalance >= 0:
        minrange = 0
    else:
        minrange = float(minbalance) * 1.1
    maxbalance = 0
    for i in df.iterrows():
        if datetime.today().date() + relativedelta(months=2) > \
                datetime.strptime(i[1].date, format).date() > datetime.today().date():
            if i[1].amount > maxbalance:
                maxbalance = i[1].amount
    maxrange = maxbalance * 1.1
    start_date = str(datetime.today().date())
    end_date = str(datetime.today().date() + relativedelta(months=2))
    layout = go.Layout(yaxis=dict(range=[minrange, maxrange]), xaxis=dict(range=[start_date, end_date]),
                       margin=dict(l=5, r=20, t=35, b=5))
    fig = px.line(df, x="date", y="amount", template="plotly", title="Cash Flow", line_shape="spline")
    fig.update_layout(layout)
    fig.update_xaxes(title_text='Date')
    fig.update_yaxes(title_text='Amount')
    fig.update_layout(paper_bgcolor="PaleTurquoise")

    graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    return render_template('index.html', title='Index', balance=balance.amount, minbalance=minbalance,
                           graphJSON=graphJSON)


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
    # create a new schedule item
    format = '%Y-%m-%d'
    if request.method == 'POST':
        name = request.form['name']
        amount = request.form['amount']
        frequency = request.form['frequency']
        startdate = request.form['startdate']
        type = request.form['type']
        schedule = Schedule(name=name,
                          type=type,
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
    # update an existing schedule item
    format = '%Y-%m-%d'

    if request.method == 'POST':
        my_data = Schedule.query.get(request.form.get('id'))
        my_data.name = request.form['name']
        my_data.amount = request.form['amount']
        my_data.type = request.form['type']
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
    # delete a schedule item
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


@main.route('/appleicon')
def appleicon():
    return send_from_directory(os.path.join(main.root_path, 'static'),
                               'apple-touch-icon.png', mimetype='image/png')


@main.route('/balance', methods=('GET', 'POST'))
@login_required
def balance():
    # manually update the balance from the balance button
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
    # change the users password from the profile page
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
    # set the settings options, in this case disable signups, from the profile page
    if request.method == 'POST':
        signupsettingname = Settings.query.filter_by(name='signup').first()

        if signupsettingname:
            signupvalue = request.form['signupvalue']
            signupsettingname.value = eval(signupvalue)
            db.session.commit()

            return redirect(url_for('main.profile'))

        # store the signup option value in the database to check when the user clicks signup
        signupvalue = request.form['signupvalue']
        signupvalue = eval(signupvalue)
        settings = Settings(name="signup",
                          value=signupvalue)
        db.session.add(settings)
        db.session.commit()

        return redirect(url_for('main.profile'))

    return redirect(url_for('main.profile'))


@main.route('/transactions')
@login_required
def transactions():
    total = Transactions.query

    return render_template('transactions_table.html', total=total)


@main.route('/email', methods=('GET', 'POST'))
@login_required
def email():
    # set the users email address, password, and server for the auto email balance update
    if request.method == 'POST':
        emailsettings = Email.query.filter_by(id=1).first()

        if emailsettings:
            email = request.form['email']
            password = request.form['password']
            server = request.form['server']
            emailsettings.email = email
            emailsettings.password = password
            emailsettings.server = server
            db.session.commit()

            return redirect(url_for('main.profile'))

        email = request.form['email']
        password = request.form['password']
        server = request.form['server']
        emailentry = Email(email=email, password=password, server=server)
        db.session.add(emailentry)
        db.session.commit()

        return redirect(url_for('main.profile'))

    return redirect(url_for('main.profile'))
