from flask import request, redirect, url_for, send_from_directory, flash, send_file
from flask_login import login_required, current_user
from flask import Blueprint, render_template
from .models import Schedule, Balance, Total, Running, User, Settings, Transactions, Email, Hold, Skip
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
    # get today's date
    todaydate = datetime.today().strftime('%A, %B %d, %Y')

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

    # calculate total events for the year amount
    calc_schedule()

    # calculate sum of running transactions
    calc_transactions(balance)

    # plot cash flow results
    minbalance, graphJSON = plot_cash()

    if current_user.admin:
        return render_template('index.html', title='Index', todaydate=todaydate, balance=balance.amount,
                           minbalance=minbalance, graphJSON=graphJSON)
    else:
        return render_template('index_guest.html', title='Index', todaydate=todaydate, balance=balance.amount,
                           minbalance=minbalance, graphJSON=graphJSON)


@main.route('/profile')
@login_required
def profile():

    if current_user.admin:
        return render_template('profile.html')
    else:
        return render_template('profile_guest.html')


@main.route('/settings')
@login_required
def settings_page():

    if current_user.admin:
        return render_template('settings.html')
    else:
        return redirect(url_for('main.index'))


@main.route('/schedule')
@login_required
def schedule():
    schedule = Schedule.query.order_by(asc(extract('day', Schedule.startdate)))

    if current_user.admin:
        return render_template('schedule_table.html', title='Schedule Table', schedule=schedule)
    else:
        return redirect(url_for('main.index'))


@main.route('/holds')
@login_required
def holds():
    hold = Hold.query
    skip = Skip.query

    if current_user.admin:
        return render_template('holds_table.html', title='Holds Table', hold=hold, skip=skip)
    else:
        return redirect(url_for('main.index'))


@main.route('/create', methods=('GET', 'POST'))
@login_required
def create():
    # create a new schedule item
    if current_user.admin:
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
            existing = Schedule.query.filter_by(name=name).first()
            if existing:
                flash("Schedule already exists")
                return redirect(url_for('main.schedule'))
            db.session.add(schedule)
            db.session.commit()
            flash("Added Successfully")

            return redirect(url_for('main.schedule'))

        return redirect(url_for('main.schedule'))
    else:
        return redirect(url_for('main.index'))


@main.route('/update', methods=['GET', 'POST'])
@login_required
def update():
    # update an existing schedule item
    if current_user.admin:
        format = '%Y-%m-%d'

        if request.method == 'POST':
            current = Schedule.query.filter_by(id=request.form['id']).first()
            existing = Schedule.query.filter_by(name=request.form['name']).first()
            if existing:
                if current.name != request.form['name']:
                    flash("Schedule name already exists")
                    return redirect(url_for('main.schedule'))
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
    else:
        return redirect(url_for('main.index'))


@main.route('/addhold/<id>')
@login_required
def addhold(id):
    # add a hold item from the schedule
    if current_user.admin:
        schedule = Schedule.query.filter_by(id=id).first()
        hold = Hold(name=schedule.name, type=schedule.type, amount=schedule.amount)
        db.session.add(hold)
        db.session.commit()

        return redirect(url_for('main.schedule'))
    else:
        return redirect(url_for('main.index'))


@main.route('/addskip/<id>')
@login_required
def addskip(id):
    # add a skip item from the schedule
    if current_user.admin:
        transaction = Transactions.query.filter_by(id=id).first()
        trans_type = ""
        if transaction.type == "Expense":
            trans_type = "Income"
        elif transaction.type == "Income":
            trans_type = "Expense"
        skip = Skip(name=transaction.name + " (SKIP)", type=trans_type, amount=transaction.amount, date=transaction.date)
        db.session.add(skip)
        db.session.commit()

        return redirect(url_for('main.transactions'))
    else:
        return redirect(url_for('main.index'))


@main.route('/deletehold/<id>')
@login_required
def holds_delete(id):
    # delete a hold item
    if current_user.admin:
        hold = Hold.query.filter_by(id=id).first()

        if hold:
            db.session.delete(hold)
            db.session.commit()
            flash("Deleted Successfully")

        return redirect(url_for('main.holds'))
    else:
        return redirect(url_for('main.index'))


@main.route('/deleteskip/<id>')
@login_required
def skips_delete(id):
    # delete a skip item
    if current_user.admin:
        skip = Skip.query.filter_by(id=id).first()

        if skip:
            db.session.delete(skip)
            db.session.commit()
            flash("Deleted Successfully")

        return redirect(url_for('main.holds'))
    else:
        return redirect(url_for('main.index'))


@main.route('/clearholds')
@login_required
def clear_holds():
    # clear holds
    if current_user.admin:
        db.session.query(Hold).delete()
        db.session.commit()

        return redirect(url_for('main.holds'))
    else:
        return redirect(url_for('main.index'))


@main.route('/clearskips')
@login_required
def clear_skips():
    # clear skips
    if current_user.admin:
        db.session.query(Skip).delete()
        db.session.commit()

        return redirect(url_for('main.index'))
    else:
        return redirect(url_for('main.index'))


@main.route('/delete/<id>')
@login_required
def schedule_delete(id):
    # delete a schedule item
    if current_user.admin:
        schedule = Schedule.query.filter_by(id=id).first()

        if schedule:
            db.session.delete(schedule)
            db.session.commit()
            flash("Deleted Successfully")

        return redirect(url_for('main.schedule'))
    else:
        return redirect(url_for('main.index'))


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
    if current_user.admin:
        format = '%Y-%m-%d'
        if request.method == 'POST':
            amount = request.form['amount']
            dateentry = request.form['date']
            balance = Balance(amount=amount,
                              date=datetime.strptime(dateentry, format).date())
            db.session.add(balance)
            db.session.commit()

            return redirect(url_for('main.index'))
    else:
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
    if current_user.admin:
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
    else:
        return redirect(url_for('main.index'))


@main.route('/transactions')
@login_required
def transactions():
    total = Transactions.query

    if current_user.admin:
        return render_template('transactions_table.html', total=total)
    else:
        return redirect(url_for('main.index'))


@main.route('/email', methods=('GET', 'POST'))
@login_required
def email():
    # set the users email address, password, and server for the auto email balance update
    if current_user.admin:
        if request.method == 'POST':
            emailsettings = Email.query.filter_by(id=1).first()

            if emailsettings:
                email = request.form['email']
                password = request.form['password']
                server = request.form['server']
                subjectstr = request.form['subject_str']
                startstr = request.form['start_str']
                endstr = request.form['end_str']
                emailsettings.email = email
                emailsettings.password = password
                emailsettings.server = server
                emailsettings.subjectstr = subjectstr
                emailsettings.startstr = startstr
                emailsettings.endstr = endstr
                db.session.commit()

                return redirect(url_for('main.profile'))

            email = request.form['email']
            password = request.form['password']
            server = request.form['server']
            subjectstr = request.form['subject_str']
            startstr = request.form['start_str']
            endstr = request.form['end_str']
            emailentry = Email(email=email, password=password, server=server, subjectstr=subjectstr, startstr=startstr,
                               endstr=endstr)
            db.session.add(emailentry)
            db.session.commit()

            return redirect(url_for('main.profile'))

        return redirect(url_for('main.profile'))
    else:
        return redirect(url_for('main.index'))


@main.route('/users_table')
@login_required
def users():
    users = User.query

    if current_user.admin:
        return render_template('users_table.html', title='Users Table', users=users)
    else:
        return redirect(url_for('main.index'))


@main.route('/update_user', methods=['GET', 'POST'])
@login_required
def update_user():
    # update an existing user
    if current_user.admin:
        if request.method == 'POST':
            current = User.query.filter_by(id=request.form['id']).first()
            existing = User.query.filter_by(email=request.form['email']).first()
            if existing:
                if current.email != request.form['email']:
                    flash("Email already exists")
                    return redirect(url_for('main.users'))
            my_data = User.query.get(request.form.get('id'))
            my_data.name = request.form['name']
            my_data.email = request.form['email']
            my_data.admin = eval(request.form['admin'])
            db.session.commit()
            flash("Updated Successfully")

            return redirect(url_for('main.users'))

        return redirect(url_for('main.users'))
    else:
        return redirect(url_for('main.index'))


@main.route('/delete_user/<id>')
@login_required
def delete_user(id):
    # delete a user
    if current_user.admin:
        user = User.query.filter_by(id=id).first()

        if user:
            db.session.delete(user)
            db.session.commit()
            flash("Deleted Successfully")

        return redirect(url_for('main.users'))
    else:
        return redirect(url_for('main.index'))


@main.route('/create_user', methods=('GET', 'POST'))
@login_required
def create_user():
    # create a new user
    if current_user.admin:
        if request.method == 'POST':
            name = request.form['name']
            email = request.form['email']
            admin = eval(request.form['admin'])
            password = generate_password_hash(request.form['password'], method='scrypt')
            user = User(name=name, email=email, admin=admin, password=password)
            existing = User.query.filter_by(email=email).first()
            if existing:
                flash("User already exists")
                return redirect(url_for('main.users'))
            db.session.add(user)
            db.session.commit()
            flash("Added Successfully")

            return redirect(url_for('main.users'))

        return redirect(url_for('main.users'))
    else:
        return redirect(url_for('main.index'))


@main.route('/manifest.json')
def serve_manifest():
    return send_file('manifest.json', mimetype='application/manifest+json')


@main.route('/sw.js')
def serve_sw():
    return send_file('sw.js', mimetype='application/javascript')
