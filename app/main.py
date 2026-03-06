from flask import request, redirect, url_for, send_from_directory, flash, send_file, Response
from flask_login import login_required, current_user
from flask import Blueprint, render_template
from .models import Schedule, Scenario, Balance, User, Settings, Email, Hold, Skip, GlobalEmailSettings, AISettings
from app import db
from datetime import datetime
import os
import json
from sqlalchemy import desc, extract, asc
from werkzeug.security import generate_password_hash, check_password_hash
from .cashflow import update_cash, plot_cash
from .auth import admin_required, global_admin_required, account_owner_required
from .files import export, upload, version
from .getemail import send_account_activation_notification
from .crypto_utils import encrypt_password, decrypt_password
from .ai_insights import fetch_insights, validate_model


main = Blueprint('main', __name__)


def get_effective_user_id():
    """
    Get the effective user ID for data filtering.
    For guest users, returns their account owner's ID.
    For account owners, returns their own ID.
    """
    if current_user.account_owner_id:
        # Guest user - return account owner's ID
        return current_user.account_owner_id
    else:
        # Account owner or standalone user - return their own ID
        return current_user.id


@main.route('/', methods=('GET', 'POST'))
@login_required
def index():
    # Get effective user ID (account owner for guests, self for owners)
    user_id = get_effective_user_id()

    # get today's date
    todaydate = datetime.today().strftime('%A, %B %d, %Y')

    # query the latest balance information for this user
    balance = Balance.query.filter_by(user_id=user_id).order_by(desc(Balance.date), desc(Balance.id)).first()

    try:
        float(balance.amount)
        db.session.query(Balance).filter_by(user_id=user_id).delete()
        balance = Balance(amount=balance.amount, date=datetime.today(), user_id=user_id)
        db.session.add(balance)
        db.session.commit()
    except:
        balance = Balance(amount='0', date=datetime.today(), user_id=user_id)
        db.session.add(balance)
        db.session.commit()

    # Pre-filter data by user before passing to cashflow
    schedules = Schedule.query.filter_by(user_id=user_id).all()
    holds = Hold.query.filter_by(user_id=user_id).all()
    skips = Skip.query.filter_by(user_id=user_id).all()
    scenarios = Scenario.query.filter_by(user_id=user_id).all()

    trans, run, run_scenario = update_cash(float(balance.amount), schedules, holds, skips, scenarios)

    # plot cash flow results
    minbalance, min_scenario, graphJSON = plot_cash(run, run_scenario)

    # Load AI insights for dashboard card (uses effective user_id so guests see owner's insights)
    ai_config = AISettings.query.filter_by(user_id=user_id).first()
    ai_insights_data = None
    ai_last_updated = None
    has_ai_key = False
    if ai_config:
        has_ai_key = bool(ai_config.api_key)
        ai_last_updated = ai_config.last_updated
        if ai_config.last_insights:
            try:
                ai_insights_data = json.loads(ai_config.last_insights)
            except Exception:
                pass

    if current_user.admin:
        return render_template('index.html', title='Index', todaydate=todaydate, balance=balance.amount,
                           minbalance=minbalance, min_scenario=min_scenario, graphJSON=graphJSON,
                           ai_insights_data=ai_insights_data, ai_last_updated=ai_last_updated,
                           has_ai_key=has_ai_key)
    else:
        return render_template('index_guest.html', title='Index', todaydate=todaydate, balance=balance.amount,
                           minbalance=minbalance, min_scenario=min_scenario, graphJSON=graphJSON,
                           ai_insights_data=ai_insights_data, ai_last_updated=ai_last_updated)


@main.route('/refresh')
@login_required
def refresh():

    return redirect(url_for('main.index'))


@main.route('/settings')
@login_required
def settings():
    # get about info - available to all users
    about = version()
    user_id = get_effective_user_id()

    if current_user.admin:
        ai_config = AISettings.query.filter_by(user_id=current_user.id).first()
        ai_configured = ai_config is not None and bool(ai_config.api_key)
        ai_model = ai_config.model_version if ai_config else ''
        email_config = Email.query.filter_by(user_id=user_id).first()
        global_email_config = GlobalEmailSettings.query.first()
        signup_setting = Settings.query.filter_by(name='signup').first()
        return render_template('settings.html', about=about, ai_configured=ai_configured, ai_model=ai_model,
                             email_config=email_config, global_email_config=global_email_config,
                             signup_setting=signup_setting)
    else:
        email_config = Email.query.filter_by(user_id=user_id).first()
        signup_setting = Settings.query.filter_by(name='signup').first()
        return render_template('settings_guest.html', about=about, email_config=email_config,
                             signup_setting=signup_setting)


@main.route('/schedule')
@login_required
@admin_required
def schedule():
    user_id = get_effective_user_id()
    schedule = Schedule.query.filter_by(user_id=user_id).order_by(asc(extract('day', Schedule.startdate)))

    return render_template('schedule_table.html', title='Schedule Table', schedule=schedule)


@main.route('/holds')
@login_required
@admin_required
def holds():
    user_id = get_effective_user_id()
    hold = Hold.query.filter_by(user_id=user_id)
    skip = Skip.query.filter_by(user_id=user_id)

    return render_template('holds_table.html', title='Holds Table', hold=hold, skip=skip)


@main.route('/create', methods=('GET', 'POST'))
@login_required
@admin_required
def create():
    # create a new schedule item
    user_id = get_effective_user_id()
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
                            startdate=datetime.strptime(startdate, format).date(),
                            firstdate=datetime.strptime(startdate, format).date(),
                            user_id=user_id)
        existing = Schedule.query.filter_by(name=name, user_id=user_id).first()
        if existing:
            flash("Schedule already exists")
            return redirect(url_for('main.schedule'))
        db.session.add(schedule)
        db.session.commit()
        flash("Added Successfully")

        return redirect(url_for('main.schedule'))

    return redirect(url_for('main.schedule'))


@main.route('/update', methods=['GET', 'POST'])
@login_required
@admin_required
def update():
    # update an existing schedule item
    user_id = get_effective_user_id()
    format = '%Y-%m-%d'

    if request.method == 'POST':
        current = Schedule.query.filter_by(id=int(request.form['id']), user_id=user_id).first()
        existing = Schedule.query.filter_by(name=request.form['name'], user_id=user_id).first()
        if existing:
            if current.name != request.form['name']:
                flash("Schedule name already exists")
                return redirect(url_for('main.schedule'))
        my_data = Schedule.query.filter_by(id=int(request.form.get('id')), user_id=user_id).first()
        my_data.name = request.form['name']
        my_data.amount = request.form['amount']
        my_data.type = request.form['type']
        my_data.frequency = request.form['frequency']
        startdate = request.form['startdate']
        if (datetime.strptime(startdate, format).date() != my_data.startdate and my_data.startdate.day !=
                datetime.strptime(startdate, format).day):
            my_data.firstdate = datetime.strptime(startdate, format).date()
        my_data.startdate = datetime.strptime(startdate, format).date()
        db.session.commit()
        flash("Updated Successfully")

        return redirect(url_for('main.schedule'))

    return redirect(url_for('main.schedule'))


@main.route('/addhold/<id>')
@login_required
@admin_required
def addhold(id):
    # add a hold item from the schedule
    user_id = get_effective_user_id()
    schedule = Schedule.query.filter_by(id=int(id), user_id=user_id).first()
    hold = Hold(name=schedule.name, type=schedule.type, amount=schedule.amount, user_id=user_id)
    db.session.add(hold)
    db.session.commit()
    flash("Added Hold")

    return redirect(url_for('main.schedule'))


@main.route('/addskip/<id>')
@login_required
@admin_required
def addskip(id):
    # add a skip item from the schedule
    user_id = get_effective_user_id()
    balance = Balance.query.filter_by(user_id=user_id).order_by(desc(Balance.date), desc(Balance.id)).first()

    # Pre-filter data by user
    schedules = Schedule.query.filter_by(user_id=user_id).all()
    holds = Hold.query.filter_by(user_id=user_id).all()
    skips = Skip.query.filter_by(user_id=user_id).all()

    trans, run, _ = update_cash(float(balance.amount), schedules, holds, skips)
    transaction = trans.loc[int(id)]
    trans_type = ""
    if transaction['type'] == "Expense":
        trans_type = "Income"
    elif transaction['type'] == "Income":
        trans_type = "Expense"
    skip = Skip(name=transaction['name'] + " (SKIP)", type=trans_type, amount=transaction['amount'], date=transaction['date'], user_id=user_id)
    db.session.add(skip)
    db.session.commit()
    flash("Added Skip")

    return redirect(url_for('main.transactions'))


@main.route('/deletehold/<id>')
@login_required
@admin_required
def holds_delete(id):
    # delete a hold item
    user_id = get_effective_user_id()
    hold = Hold.query.filter_by(id=int(id), user_id=user_id).first()

    if hold:
        db.session.delete(hold)
        db.session.commit()
        flash("Deleted Successfully")

    return redirect(url_for('main.holds'))


@main.route('/deleteskip/<id>')
@login_required
@admin_required
def skips_delete(id):
    # delete a skip item
    user_id = get_effective_user_id()
    skip = Skip.query.filter_by(id=int(id), user_id=user_id).first()

    if skip:
        db.session.delete(skip)
        db.session.commit()
        flash("Deleted Successfully")

    return redirect(url_for('main.holds'))


@main.route('/clearholds')
@login_required
@admin_required
def clear_holds():
    # clear holds
    user_id = get_effective_user_id()
    db.session.query(Hold).filter_by(user_id=user_id).delete()
    db.session.commit()

    return redirect(url_for('main.holds'))


@main.route('/clearskips')
@login_required
@admin_required
def clear_skips():
    # clear skips
    user_id = get_effective_user_id()
    db.session.query(Skip).filter_by(user_id=user_id).delete()
    db.session.commit()

    return redirect(url_for('main.holds'))


@main.route('/delete/<id>')
@login_required
@admin_required
def schedule_delete(id):
    # delete a schedule item
    user_id = get_effective_user_id()
    schedule = Schedule.query.filter_by(id=int(id), user_id=user_id).first()

    if schedule:
        db.session.delete(schedule)
        db.session.commit()
        flash("Deleted Successfully")

    return redirect(url_for('main.schedule'))


@main.route('/scenarios')
@login_required
@admin_required
def scenarios():
    user_id = get_effective_user_id()
    scenario = Scenario.query.filter_by(user_id=user_id).order_by(asc(extract('day', Scenario.startdate)))

    return render_template('scenario_table.html', title='Scenario Table', scenario=scenario)


@main.route('/create_scenario', methods=('GET', 'POST'))
@login_required
@admin_required
def create_scenario():
    user_id = get_effective_user_id()
    format = '%Y-%m-%d'
    if request.method == 'POST':
        name = request.form['name']
        amount = request.form['amount']
        frequency = request.form['frequency']
        startdate = request.form['startdate']
        type = request.form['type']
        scenario = Scenario(name=name,
                            type=type,
                            amount=amount,
                            frequency=frequency,
                            startdate=datetime.strptime(startdate, format).date(),
                            firstdate=datetime.strptime(startdate, format).date(),
                            user_id=user_id)
        existing = Scenario.query.filter_by(name=name, user_id=user_id).first()
        if existing:
            flash("Scenario already exists")
            return redirect(url_for('main.scenarios'))
        db.session.add(scenario)
        db.session.commit()
        flash("Added Successfully")

        return redirect(url_for('main.scenarios'))

    return redirect(url_for('main.scenarios'))


@main.route('/update_scenario', methods=['GET', 'POST'])
@login_required
@admin_required
def update_scenario():
    user_id = get_effective_user_id()
    format = '%Y-%m-%d'

    if request.method == 'POST':
        current = Scenario.query.filter_by(id=int(request.form['id']), user_id=user_id).first()
        if not current:
            flash("Scenario not found")
            return redirect(url_for('main.scenarios'))
        existing = Scenario.query.filter_by(name=request.form['name'], user_id=user_id).first()
        if existing and current.name != request.form['name']:
            flash("Scenario name already exists")
            return redirect(url_for('main.scenarios'))
        current.name = request.form['name']
        current.amount = request.form['amount']
        current.type = request.form['type']
        current.frequency = request.form['frequency']
        startdate = request.form['startdate']
        if (datetime.strptime(startdate, format).date() != current.startdate and current.startdate.day !=
                datetime.strptime(startdate, format).day):
            current.firstdate = datetime.strptime(startdate, format).date()
        current.startdate = datetime.strptime(startdate, format).date()
        db.session.commit()
        flash("Updated Successfully")

        return redirect(url_for('main.scenarios'))

    return redirect(url_for('main.scenarios'))


@main.route('/delete_scenario/<id>')
@login_required
@admin_required
def scenario_delete(id):
    user_id = get_effective_user_id()
    scenario = Scenario.query.filter_by(id=int(id), user_id=user_id).first()

    if scenario:
        db.session.delete(scenario)
        db.session.commit()
        flash("Deleted Successfully")

    return redirect(url_for('main.scenarios'))


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
@admin_required
def balance():
    # manually update the balance from the balance button
    user_id = get_effective_user_id()
    format = '%Y-%m-%d'
    if request.method == 'POST':
        amount = request.form['amount']
        dateentry = request.form['date']
        balance = Balance(amount=amount,
                          date=datetime.strptime(dateentry, format).date(),
                          user_id=user_id)
        db.session.add(balance)
        db.session.commit()

        return redirect(url_for('main.index'))


@main.route('/changepw', methods=('GET', 'POST'))
@login_required
def changepw():
    # update account profile (name, email) and optionally change password
    if request.method == 'POST':
        my_user = User.query.filter_by(id=current_user.id).first()
        current = request.form['current']
        new_name = request.form.get('name', '').strip()
        new_email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        password2 = request.form.get('password2', '').strip()

        if not check_password_hash(my_user.password, current):
            flash('Incorrect current password')
            return redirect(url_for('main.settings'))

        # Validate new email if it changed
        if new_email and new_email != my_user.email.lower():
            existing = User.query.filter(
                db.func.lower(User.email) == new_email,
                User.id != my_user.id
            ).first()
            if existing:
                flash('That email address is already in use')
                return redirect(url_for('main.settings'))
            my_user.email = new_email

        if new_name:
            my_user.name = new_name

        # Only update password if the user filled in the new password fields
        if password or password2:
            if password != password2:
                flash('New passwords do not match')
                return redirect(url_for('main.settings'))
            my_user.password = generate_password_hash(password, method='scrypt')

        db.session.commit()
        flash('Account settings updated successfully')
        return redirect(url_for('main.settings'))

    return redirect(url_for('main.settings'))


@main.route('/signups', methods=('GET', 'POST'))
@login_required
@global_admin_required
def signups():
    # set the settings options, in this case disable signups, from the profile page
    if request.method == 'POST':
        signupsettingname = Settings.query.filter_by(name='signup').first()

        if signupsettingname:
            if request.form['signupvalue'] == "True":
                signupvalue = True
            else:
                signupvalue = False
            signupsettingname.value = signupvalue
            db.session.commit()

            return redirect(url_for('main.settings'))

        # store the signup option value in the database to check when the user clicks signup
        if request.form['signupvalue'] == "True":
            signupvalue = True
        else:
            signupvalue = False
        settings = Settings(name="signup", value=signupvalue)
        db.session.add(settings)
        db.session.commit()

        return redirect(url_for('main.settings'))

    return redirect(url_for('main.settings'))


@main.route('/transactions')
@login_required
@admin_required
def transactions():
    user_id = get_effective_user_id()
    balance = Balance.query.filter_by(user_id=user_id).order_by(desc(Balance.date), desc(Balance.id)).first()

    # Pre-filter data by user
    schedules = Schedule.query.filter_by(user_id=user_id).all()
    holds = Hold.query.filter_by(user_id=user_id).all()
    skips = Skip.query.filter_by(user_id=user_id).all()

    trans, run, _ = update_cash(float(balance.amount), schedules, holds, skips)

    return render_template('transactions_table.html', total=trans.to_dict(orient='records'))


@main.route('/email', methods=('GET', 'POST'))
@login_required
@admin_required
def email():
    # set the users email address, password, and server for the auto email balance update
    user_id = get_effective_user_id()

    if request.method == 'POST':
        emailsettings = Email.query.filter_by(user_id=user_id).first()

        if emailsettings:
            email = request.form['email']
            password_input = request.form.get('password', '').strip()
            server = request.form['server']
            subjectstr = request.form['subject_str']
            startstr = request.form['start_str']
            endstr = request.form['end_str']
            emailsettings.email = email
            if password_input:
                emailsettings.password = encrypt_password(password_input)
            emailsettings.server = server
            emailsettings.subjectstr = subjectstr
            emailsettings.startstr = startstr
            emailsettings.endstr = endstr
            db.session.commit()

            return redirect(url_for('main.settings'))

        email = request.form['email']
        password = encrypt_password(request.form['password'])
        server = request.form['server']
        subjectstr = request.form['subject_str']
        startstr = request.form['start_str']
        endstr = request.form['end_str']
        emailentry = Email(email=email, password=password, server=server, subjectstr=subjectstr, startstr=startstr,
                           endstr=endstr, user_id=user_id)
        db.session.add(emailentry)
        db.session.commit()

        return redirect(url_for('main.settings'))

    return redirect(url_for('main.settings'))


@main.route('/update_user', methods=['GET', 'POST'])
@login_required
@admin_required
def update_user():
    # update an existing user
    if request.method == 'POST':
        current = User.query.filter_by(id=int(request.form['id'])).first()

        # Check if the current user has permission to update this user
        if not current_user.is_global_admin and current.account_owner_id != current_user.id:
            flash("You don't have permission to update this user")
            if current_user.is_global_admin:
                return redirect(url_for('main.global_admin_panel'))
            else:
                return redirect(url_for('main.manage_guests'))

        existing = User.query.filter_by(email=request.form['email']).first()
        if existing:
            if current.email != request.form['email']:
                flash("Email already exists")
                if current_user.is_global_admin:
                    return redirect(url_for('main.global_admin_panel'))
                else:
                    return redirect(url_for('main.manage_guests'))
        my_data = User.query.get(request.form.get('id'))
        my_data.name = request.form['name']
        my_data.email = request.form['email']

        # Global admins can change roles, regular admins cannot
        if current_user.is_global_admin:
            # Handle role assignment
            role = request.form.get('role', 'user')
            if role == 'global_admin':
                my_data.admin = True
                my_data.is_global_admin = True
                # IMPORTANT: Global admins must always be active
                my_data.is_active = True
            elif role == 'admin':
                my_data.admin = True
                my_data.is_global_admin = False
            else:  # user
                my_data.admin = False
                my_data.is_global_admin = False

        db.session.commit()
        flash("Updated Successfully")

        # Redirect based on user role
        if current_user.is_global_admin:
            return redirect(url_for('main.global_admin_panel'))
        else:
            return redirect(url_for('main.manage_guests'))

    # Redirect based on user role
    if current_user.is_global_admin:
        return redirect(url_for('main.global_admin_panel'))
    else:
        return redirect(url_for('main.manage_guests'))


@main.route('/delete_user/<id>')
@login_required
@admin_required
def delete_user(id):
    # delete a user
    user = User.query.filter_by(id=int(id)).first()

    if user:
        # Global admins can delete any user (except themselves), regular admins can only delete their guests
        if current_user.is_global_admin or user.account_owner_id == current_user.id:
            # Prevent deleting yourself
            if user.id == current_user.id:
                flash("You cannot delete your own account")
                if current_user.is_global_admin:
                    return redirect(url_for('main.global_admin_panel'))
                else:
                    return redirect(url_for('main.manage_guests'))

            # Manually delete all related data before deleting the user
            user_id = user.id

            # Delete all guest users for this admin user
            db.session.query(User).filter_by(account_owner_id=user_id).delete()

            # Delete all schedules for this user
            db.session.query(Schedule).filter_by(user_id=user_id).delete()

            # Delete all scenarios for this user
            db.session.query(Scenario).filter_by(user_id=user_id).delete()

            # Delete all balances for this user
            db.session.query(Balance).filter_by(user_id=user_id).delete()

            # Delete all holds for this user
            db.session.query(Hold).filter_by(user_id=user_id).delete()

            # Delete all skips for this user
            db.session.query(Skip).filter_by(user_id=user_id).delete()

            # Delete all email configs for this user
            db.session.query(Email).filter_by(user_id=user_id).delete()

            # Now delete the user
            db.session.delete(user)
            db.session.commit()
            flash("Deleted Successfully")
        else:
            flash("You don't have permission to delete this user")

    # Redirect based on user role
    if current_user.is_global_admin:
        return redirect(url_for('main.global_admin_panel'))
    else:
        return redirect(url_for('main.manage_guests'))


@main.route('/activate_user/<id>')
@login_required
@admin_required
def activate_user(id):
    # activate a user account
    user = User.query.filter_by(id=int(id)).first()

    if user:
        # Global admins can activate any user, regular admins can only activate their guests
        if current_user.is_global_admin or user.account_owner_id == current_user.id:
            user.is_active = True
            db.session.commit()
            flash(f"User {user.name} has been activated successfully")

            # Send activation notification email to the user
            try:
                send_account_activation_notification(user.name, user.email)
            except Exception as e:
                # Don't fail activation if email notification fails
                print(f"Failed to send activation notification to {user.email}: {e}")
        else:
            flash("You don't have permission to activate this user")

    # Redirect based on user role
    if current_user.is_global_admin:
        return redirect(url_for('main.global_admin_panel'))
    else:
        return redirect(url_for('main.manage_guests'))


@main.route('/deactivate_user/<id>')
@login_required
@admin_required
def deactivate_user(id):
    # deactivate a user account
    user = User.query.filter_by(id=int(id)).first()

    if user:
        # IMPORTANT: Global admins are always active and cannot be deactivated
        if user.is_global_admin:
            flash("Cannot deactivate a global admin. Global admins must always remain active.")
            if current_user.is_global_admin:
                return redirect(url_for('main.global_admin_panel'))
            else:
                return redirect(url_for('main.manage_guests'))

        # Global admins can deactivate any user, regular admins can only deactivate their guests
        if current_user.is_global_admin or user.account_owner_id == current_user.id:
            user.is_active = False
            db.session.commit()
            flash(f"User {user.name} has been deactivated successfully")
        else:
            flash("You don't have permission to deactivate this user")

    # Redirect based on user role
    if current_user.is_global_admin:
        return redirect(url_for('main.global_admin_panel'))
    else:
        return redirect(url_for('main.manage_guests'))


@main.route('/create_user', methods=('GET', 'POST'))
@login_required
@admin_required
def create_user():
    # create a new user
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'], method='scrypt')

        # Handle role assignment
        role = request.form.get('role', 'user')

        # Global admins can create any type of user
        if current_user.is_global_admin:
            if role == 'global_admin':
                admin = True
                is_global_admin = True
            elif role == 'admin':
                admin = True
                is_global_admin = False
            else:  # user
                admin = False
                is_global_admin = False
            account_owner_id = None
            # Users created by global admin are active by default
            is_active = True
        else:
            # Regular admins can only create guest users (non-admin users)
            admin = False
            is_global_admin = False
            account_owner_id = current_user.id
            # Guests created by regular admins are active by default
            is_active = True

        user = User(name=name, email=email, admin=admin, is_global_admin=is_global_admin,
                    is_active=is_active, password=password, account_owner_id=account_owner_id)
        existing = User.query.filter_by(email=email).first()
        if existing:
            flash("User already exists")
            if current_user.is_global_admin:
                return redirect(url_for('main.global_admin_panel'))
            else:
                return redirect(url_for('main.manage_guests'))
        db.session.add(user)
        db.session.commit()
        flash("Added Successfully")

        # Redirect based on user role
        if current_user.is_global_admin:
            return redirect(url_for('main.global_admin_panel'))
        else:
            return redirect(url_for('main.manage_guests'))

    # Redirect based on user role
    if current_user.is_global_admin:
        return redirect(url_for('main.global_admin_panel'))
    else:
        return redirect(url_for('main.manage_guests'))


@main.route('/export', methods=('GET', 'POST'))
@login_required
@admin_required
def export_csv():
    user_id = get_effective_user_id()

    csv_data = export(user_id)

    # Create a direct download response with the CSV data and appropriate headers
    response = Response(csv_data, content_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=schedule_export.csv"

    return response


@main.route('/import', methods=('GET', 'POST'))
@login_required
@admin_required
def import_csv():
    if request.method == 'POST':
        user_id = get_effective_user_id()
        csv_file = request.files.get('file')

        upload(csv_file, user_id)

        flash("Import Successful")

    return redirect(url_for('main.schedule'))


@main.route('/manage_guests')
@login_required
@account_owner_required
def manage_guests():
    """Account owners can manage their guest users"""
    guests = User.query.filter_by(account_owner_id=current_user.id).all()
    return render_template('manage_guests.html', guests=guests)


@main.route('/add_guest', methods=['POST'])
@login_required
@account_owner_required
def add_guest():
    """Create a guest user linked to current account owner"""
    email = request.form.get('email')
    name = request.form.get('name')

    # Check if user already exists
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        flash('A user with this email already exists')
        return redirect(url_for('main.manage_guests'))

    # Generate a random password for guest (they can change it later)
    import secrets
    temp_password = secrets.token_urlsafe(16)

    new_guest = User(
        email=email,
        name=name,
        password=generate_password_hash(temp_password, method='scrypt'),
        admin=False,  # Guests are not admins
        is_global_admin=False,
        account_owner_id=current_user.id
    )
    db.session.add(new_guest)
    db.session.commit()

    flash(f'Guest user {name} added successfully. Temporary password: {temp_password}')
    return redirect(url_for('main.manage_guests'))


@main.route('/remove_guest/<int:guest_id>', methods=['POST'])
@login_required
@account_owner_required
def remove_guest(guest_id):
    """Remove a guest user (account owner only)"""
    guest = User.query.filter_by(id=int(guest_id), account_owner_id=current_user.id).first()

    if guest:
        db.session.delete(guest)
        db.session.commit()
        flash('Guest user removed successfully')
    else:
        flash('Guest user not found or you do not have permission to remove them')

    return redirect(url_for('main.manage_guests'))


@main.route('/global_admin')
@login_required
@global_admin_required
def global_admin_panel():
    """Global admin can see all users and accounts"""
    all_users = User.query.all()

    # Organize users by account owners
    account_owners = [u for u in all_users if u.account_owner_id is None and not u.is_global_admin]
    global_admins = [u for u in all_users if u.is_global_admin]
    standalone_users = [u for u in all_users if u.account_owner_id is None and not u.admin]

    return render_template('global_admin.html',
                         all_users=all_users,
                         account_owners=account_owners,
                         global_admins=global_admins,
                         standalone_users=standalone_users)


@main.route('/global_email_settings', methods=['GET', 'POST'])
@login_required
@global_admin_required
def global_email_settings():
    """Configure global email settings for all email notifications"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        smtp_server = request.form.get('smtp_server')

        # Check if global settings already exist
        settings = GlobalEmailSettings.query.first()

        if settings:
            # Update existing settings
            settings.email = email
            if password:
                settings.password = encrypt_password(password)
            settings.smtp_server = smtp_server
        else:
            # Create new settings
            settings = GlobalEmailSettings(
                id=1,  # Enforce single row
                email=email,
                password=encrypt_password(password),
                smtp_server=smtp_server
            )
            db.session.add(settings)

        db.session.commit()
        flash('Global email settings saved successfully')
        return redirect(url_for('main.settings'))

    return redirect(url_for('main.settings'))


@main.route('/ai_settings', methods=['POST'])
@login_required
@admin_required
def ai_settings():
    """Save the user's OpenAI API key (encrypted) and optional model selection."""
    api_key_input = request.form.get('api_key', '').strip()
    model_input = request.form.get('model_version', '').strip()

    ai_config = AISettings.query.filter_by(user_id=current_user.id).first()

    if not api_key_input:
        if not ai_config or not ai_config.api_key:
            flash('API key cannot be empty', 'error')
            return redirect(url_for('main.settings'))
        # No new key provided but one is already stored — update model only
        if model_input:
            plaintext_key = decrypt_password(ai_config.api_key)
            valid, err = validate_model(plaintext_key, model_input)
            if not valid:
                flash(err, 'error')
                return redirect(url_for('main.settings'))
        ai_config.model_version = model_input or None
    else:
        if model_input:
            valid, err = validate_model(api_key_input, model_input)
            if not valid:
                flash(err, 'error')
                return redirect(url_for('main.settings'))
        encrypted_key = encrypt_password(api_key_input)
        if ai_config:
            ai_config.api_key = encrypted_key
            ai_config.model_version = model_input or None
        else:
            ai_config = AISettings(user_id=current_user.id, api_key=encrypted_key, model_version=model_input or None)
            db.session.add(ai_config)

    db.session.commit()
    flash('AI settings saved successfully')
    return redirect(url_for('main.settings'))


@main.route('/ai_insights', methods=['POST'])
@login_required
@admin_required
def ai_insights():
    """Query OpenAI for cash flow insights on demand and cache the result."""
    user_id = current_user.id

    ai_config = AISettings.query.filter_by(user_id=user_id).first()
    if not ai_config or not ai_config.api_key:
        return Response(json.dumps({'error': 'No OpenAI API key configured. Please add one in Settings.'}),
                        status=400, mimetype='application/json')

    balance_record = Balance.query.filter_by(user_id=user_id).order_by(desc(Balance.date), desc(Balance.id)).first()
    current_balance = float(balance_record.amount) if balance_record else 0.0

    schedules = Schedule.query.filter_by(user_id=user_id).all()
    holds = Hold.query.filter_by(user_id=user_id).all()
    skips = Skip.query.filter_by(user_id=user_id).all()

    try:
        insights_json = fetch_insights(ai_config.api_key, current_balance, schedules, holds, skips, model=ai_config.model_version)
    except Exception as e:
        return Response(json.dumps({'error': str(e)}), status=500, mimetype='application/json')

    ai_config.last_insights = insights_json
    ai_config.last_updated = datetime.utcnow()
    db.session.commit()

    return Response(insights_json, status=200, mimetype='application/json')


@main.route('/manifest.json')
def serve_manifest():
    return send_file('manifest.json', mimetype='application/manifest+json')


@main.route('/sw.js')
def serve_sw():
    return send_file('sw.js', mimetype='application/javascript')
