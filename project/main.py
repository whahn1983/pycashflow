from flask import Flask, render_template, request, abort, redirect, url_for, config, send_from_directory
from flask_login import login_required, current_user
from flask import Blueprint, render_template
from .models import Schedule, Balance, Total
from . import db
from datetime import datetime
import pandas as pd
import json
import plotly
import plotly.express as px
import os
from sqlalchemy import desc, and_, select

main = Blueprint('main', __name__)


@main.route('/')
@login_required
def index():
    balance = Balance.query.order_by(desc(Balance.date)).first()
    return render_template('index.html', title='Index', balance=balance.amount)


@main.route('/api/data')
@login_required
def data():
    query = Schedule.query

    # search filter
    search = request.args.get('search[value]')
    if search:
        query = query.filter(db.or_(
            Schedule.name.like(f'%{search}%'),
            Schedule.amount.like(f'%{search}%'),
            Schedule.frequency.like(f'%{search}%'),
            Schedule.startdate.like(f'%{search}%'),
        ))
    total_filtered = query.count()

    # sorting
    order = []
    i = 0
    while True:
        col_index = request.args.get(f'order[{i}][column]')
        if col_index is None:
            break
        col_name = request.args.get(f'columns[{col_index}][data]')
        if col_name not in ['name', 'amount', 'frequency', 'startdate']:
            col_name = 'name'
        descending = request.args.get(f'order[{i}][dir]') == 'desc'
        col = getattr(Schedule, col_name)
        if descending:
            col = col.desc()
        order.append(col)
        i += 1
    if order:
        query = query.order_by(*order)

    # pagination
    start = request.args.get('start', type=int)
    length = request.args.get('length', type=int)
    query = query.offset(start).limit(length)

    # response
    return {
        'data': [schedule.to_dict() for schedule in query],
        'recordsFiltered': total_filtered,
        'recordsTotal': Schedule.query.count(),
        'draw': request.args.get('draw', type=int),
    }


@main.route('/profile')
@login_required
def profile():

    return render_template('profile.html', name="William Hahn")


@main.route('/schedule')
@login_required
def schedule():
    schedule = Schedule.query
    return render_template('schedule_table.html', title='Schedule Table',
                           schedule=schedule)


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

        return redirect(url_for('main.index'))

    return render_template('create.html')


@main.route('/delete')
@login_required
def schedule_delete(mid):
    schedule = Schedule.query.filter_by(id=mid).first()
    if schedule:
        db.session.delete(schedule)
        db.session.commit()
    return redirect(url_for('main.schedule'))


@main.route('/report')
@login_required
def report():
    return render_template('report.html', graphJSON=report_gen())

def report_gen():
    engine = db.create_engine('sqlite:///instance/db.sqlite').connect()

    df = pd.read_sql('SELECT * FROM schedule;', engine)

    fig = px.line(df, x="startdate", y="amount")

    graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    return graphJSON


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
        date = request.form['date']
        balance = Balance(amount=amount,
                          date=datetime.strptime(date, format).date())
        db.session.add(balance)
        db.session.commit()

        return redirect(url_for('main.index'))

    return render_template('balance.html')
