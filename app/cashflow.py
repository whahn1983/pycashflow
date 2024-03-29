from app import db
from .models import Schedule, Total, Running, Transactions, Skip, Balance
from datetime import datetime, date
import pandas as pd
import json
import plotly
import plotly.express as px
import os
from dateutil.relativedelta import relativedelta
from natsort import index_natsorted
import numpy as np
import decimal
import plotly.graph_objs as go
from pathlib import Path


def update_cash(balance, refresh):
    # if the database has been modified, update the calculations
    try:
        modifiedtime = os.path.getmtime(os.environ.get('DATABASE_URL').replace('sqlite:///', ''))
        modifiedtime = datetime.fromtimestamp(modifiedtime)
        modpath = os.environ.get('DATABASE_URL').replace('sqlite:///', '')
        modpath = modpath.replace('db.sqlite', 'modified')
        os.close(os.open(modpath, os.O_CREAT))
        dbmodified = os.path.getmtime(modpath)
        dbmodified = datetime.fromtimestamp(dbmodified)
    except:
        basedir = os.path.abspath(os.path.dirname(__file__))
        datafile = os.path.join(basedir, "data/db.sqlite")
        modifiedtime = os.path.getmtime(datafile)
        modifiedtime = datetime.fromtimestamp(modifiedtime)
        modpath = os.path.join(basedir, "data/modified")
        os.close(os.open(modpath, os.O_CREAT))
        dbmodified = os.path.getmtime(modpath)
        dbmodified = datetime.fromtimestamp(dbmodified)

    dt = date.today()
    today = datetime.combine(dt, datetime.min.time())

    if modifiedtime > dbmodified or dbmodified < today or refresh == 1:
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

        Path(modpath).touch()


def calc_schedule():
    months = 13
    weeks = 53
    years = 1
    quarters = 4
    biweeks = 27

    try:
        engine = db.create_engine(os.environ.get('DATABASE_URL')).connect()
    except:
        engine = db.create_engine('sqlite:///db.sqlite').connect()

    # pull the schedule information
    df = pd.read_sql('SELECT * FROM schedule;', engine)

    # loop through the schedule and create transactions in a table out to the future number of years
    todaydate = datetime.today().date()
    for i in range(len(df.index)):
        format = '%Y-%m-%d'
        name = df['name'][i]
        startdate = df['startdate'][i]
        firstdate = df['firstdate'][i]
        frequency = df['frequency'][i]
        amount = df['amount'][i]
        type = df['type'][i]
        existing = Schedule.query.filter_by(name=name).first()
        if not firstdate:
            existing.firstdate = datetime.strptime(startdate, format).date()
            firstdate = existing.firstdate.strftime(format)
            db.session.commit()
        if frequency == 'Monthly':
            for k in range(months):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(months=k)
                futuredateday = futuredate.day
                firstdateday = datetime.strptime(firstdate, format).date().day
                if firstdateday > futuredateday:
                    try:
                        for m in range(3):
                            futuredateday += 1
                            if firstdateday >= futuredateday:
                                futuredate = futuredate.replace(day=futuredateday)
                    except ValueError:
                        pass
                if futuredate <= todaydate and datetime.today().weekday() < 5:
                    existing.startdate = futuredate + relativedelta(months=1)
                    daycheckdate = futuredate + relativedelta(months=1)
                    daycheck = daycheckdate.day
                    if firstdateday > daycheck:
                        try:
                            for m in range(3):
                                daycheck += 1
                                if firstdateday >= daycheck:
                                    existing.startdate = daycheckdate.replace(day=daycheck)
                        except ValueError:
                            pass
                if type == 'Income':
                    rollbackdate = datetime.combine(futuredate, datetime.min.time())
                    total = Total(type=type, name=name, amount=amount,
                                  date=pd.tseries.offsets.BDay(1).rollback(rollbackdate).date())
                else:
                    total = Total(type=type, name=name, amount=amount, date=futuredate - pd.tseries.offsets.BDay(0))
                db.session.add(total)
        elif frequency == 'Weekly':
            for k in range(weeks):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(weeks=k)
                if futuredate <= todaydate and datetime.today().weekday() < 5:
                    existing.startdate = futuredate + relativedelta(weeks=1)
                total = Total(type=type, name=name, amount=amount, date=futuredate - pd.tseries.offsets.BDay(0))
                db.session.add(total)
        elif frequency == 'Yearly':
            for k in range(years):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(years=k)
                if futuredate <= todaydate and datetime.today().weekday() < 5:
                    existing.startdate = futuredate + relativedelta(years=1)
                total = Total(type=type, name=name, amount=amount, date=futuredate - pd.tseries.offsets.BDay(0))
                db.session.add(total)
        elif frequency == 'Quarterly':
            for k in range(quarters):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(months=3 * k)
                futuredateday = futuredate.day
                firstdateday = datetime.strptime(firstdate, format).date().day
                if firstdateday > futuredateday:
                    try:
                        for m in range(3):
                            futuredateday += 1
                            if firstdateday >= futuredateday:
                                futuredate = futuredate.replace(day=futuredateday)
                    except ValueError:
                        pass
                if futuredate <= todaydate and datetime.today().weekday() < 5:
                    existing.startdate = futuredate + relativedelta(months=3)
                    daycheckdate = futuredate + relativedelta(months=3)
                    daycheck = daycheckdate.day
                    if firstdateday > daycheck:
                        try:
                            for m in range(3):
                                daycheck += 1
                                if firstdateday >= daycheck:
                                    existing.startdate = daycheckdate.replace(day=daycheck)
                        except ValueError:
                            pass
                total = Total(type=type, name=name, amount=amount, date=futuredate - pd.tseries.offsets.BDay(0))
                db.session.add(total)
        elif frequency == 'BiWeekly':
            for k in range(biweeks):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(weeks=2 * k)
                if futuredate <= todaydate and datetime.today().weekday() < 5:
                    existing.startdate = futuredate + relativedelta(weeks=2)
                total = Total(type=type, name=name, amount=amount, date=futuredate - pd.tseries.offsets.BDay(0))
                db.session.add(total)
        elif frequency == 'Onetime':
            futuredate = datetime.strptime(startdate, format).date()
            if futuredate < todaydate:
                db.session.delete(existing)
            else:
                total = Total(type=type, name=name, amount=amount, date=futuredate)
                db.session.add(total)
    db.session.commit()

    # add the hold items
    df = pd.read_sql('SELECT * FROM hold;', engine)
    for i in range(len(df.index)):
        name = df['name'][i]
        amount = df['amount'][i]
        type = df['type'][i]
        total = Total(type=type, name=name, amount=amount, date=todaydate + relativedelta(days=1))
        db.session.add(total)
    db.session.commit()

    # add the skip items
    df = pd.read_sql('SELECT * FROM skip;', engine)
    for i in range(len(df.index)):
        format = '%Y-%m-%d'
        name = df['name'][i]
        amount = df['amount'][i]
        type = df['type'][i]
        date = df['date'][i]
        if datetime.strptime(date, format).date() < todaydate:
            skip = Skip.query.filter_by(name=name).first()
            db.session.delete(skip)
        else:
            total = Total(type=type, name=name, amount=amount, date=datetime.strptime(date, format).date())
            db.session.add(total)
    db.session.commit()


def calc_transactions(balance):
    try:
        engine = db.create_engine(os.environ.get('DATABASE_URL')).connect()
    except:
        engine = db.create_engine('sqlite:///db.sqlite').connect()

    # retrieve the total future transactions
    df = pd.read_sql('SELECT * FROM total;', engine)
    df = df.sort_values(by="date", key=lambda x: np.argsort(index_natsorted(df["date"])))

    # collect the next 60 days of transactions for the transactions table
    format = '%Y-%m-%d'
    todaydate = datetime.today().date()
    todaydateplus = todaydate + relativedelta(months=2)
    for i in df.iterrows():
        if todaydateplus > \
                datetime.strptime(i[1].date, format).date() > todaydate and "(SKIP)" not in i[1].iloc[3]:
            transactions = Transactions(name=i[1].iloc[3], type=i[1].type, amount=i[1].amount,
                                        date=datetime.strptime(i[1].date, format).date())
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
        if datetime.strptime(rundate, format).date() > todaydate:
            runbalance += amount
            running = Running(amount=runbalance, date=datetime.strptime(rundate, format).date())
            db.session.add(running)
    db.session.commit()


def plot_cash():
    try:
        engine = db.create_engine(os.environ.get('DATABASE_URL')).connect()
    except:
        engine = db.create_engine('sqlite:///db.sqlite').connect()

    # plot the running balances by date on a line plot
    df = pd.read_sql('SELECT * FROM running;', engine)
    df = df.sort_values(by='date', ascending=False)
    format = '%Y-%m-%d'
    minbalance = df['amount'].min()
    minbalance = decimal.Decimal(str(minbalance)).quantize(decimal.Decimal('.01'))
    if float(minbalance) >= 0:
        minrange = 0
    else:
        minrange = float(minbalance) * 1.1
    maxbalance = 0
    todaydate = datetime.today().date()
    todaydateplus = todaydate + relativedelta(months=2)
    for i in df.iterrows():
        if todaydateplus > datetime.strptime(i[1].date, format).date() > todaydate:
            if i[1].amount > maxbalance:
                maxbalance = i[1].amount
    maxrange = maxbalance * 1.1
    start_date = str(datetime.today().date())
    end_date = str(datetime.today().date() + relativedelta(months=2))
    layout = go.Layout(yaxis=dict(range=[minrange, maxrange]), xaxis=dict(range=[start_date, end_date]),
                       margin=dict(l=5, r=20, t=35, b=5), dragmode='pan')
    fig = px.line(df, x="date", y="amount", template="plotly", title="Cash Flow", line_shape="spline")
    fig.update_layout(layout)
    fig.update_xaxes(title_text='Date')
    fig.update_yaxes(title_text='Amount')
    fig.update_layout(paper_bgcolor="PaleTurquoise")

    graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    return minbalance, graphJSON