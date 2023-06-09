from flask import request, redirect, url_for, send_from_directory, flash
from flask_login import login_required, current_user
from flask import Blueprint, render_template
from .models import Schedule, Balance, Total, Running, User, Settings, Transactions, Email
from app import db
from datetime import datetime
import os
from sqlalchemy import desc, extract, asc
from werkzeug.security import generate_password_hash
from .cashflow import calc_schedule, calc_transactions, plot_cash


main = Blueprint('main', __name__)


@main.route('/', methods=('GET', 'POST'))
@login_required
def index():
    # query the latest balance information
    balance = Balance.query.order_by(desc(Balance.date), desc(Balance.id)).first()

    try:
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

    # empty the tables to create fresh data from the schedule
    db.session.query(Total).delete()
    db.session.query(Running).delete()
    db.session.query(Transactions).delete()
    db.session.commit()

    # retrieve the number of years for the cash flow plot
    yearamount = request.form.get('yearamount')

    # calculate total events for the year amount
    calc_schedule(yearamount)

    # calculate sum of running transactions
    calc_transactions(balance)

    # plot cash flow results
    minbalance, graphJSON = plot_cash()

    return render_template('index.html', title='Index', balance=balance.amount, minbalance=minbalance,
                           graphJSON=graphJSON)


@main.route('/profile')
@login_required
def profile():

    return render_template('profile.html')


@main.route('/schedule')
@login_required
def schedule():
    schedule = Schedule.query.order_by(asc(extract('day', Schedule.startdate)))

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
