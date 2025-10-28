from app import db
from .models import Schedule, Skip
from datetime import datetime, date
import pandas as pd
import json
import plotly
import os
from dateutil.relativedelta import relativedelta
from natsort import index_natsorted
import numpy as np
import decimal
import plotly.graph_objs as go


def update_cash(balance, schedules, holds, skips):
    """
    Calculate cash flow with pre-filtered user data

    Args:
        balance: Current balance amount (Decimal)
        schedules: List of Schedule objects (pre-filtered for user)
        holds: List of Hold objects (pre-filtered for user)
        skips: List of Skip objects (pre-filtered for user)

    Returns:
        trans: DataFrame of upcoming transactions
        run: DataFrame of running balance projections
    """
    # calculate total events for the year amount
    total = calc_schedule(schedules, holds, skips)

    # calculate sum of running transactions
    trans, run = calc_transactions(balance, total)

    return trans, run


def calc_schedule(schedules, holds, skips):
    """
    Process schedules, holds, and skips into projected transactions

    Args:
        schedules: List of Schedule objects (pre-filtered for user)
        holds: List of Hold objects (pre-filtered for user)
        skips: List of Skip objects (pre-filtered for user)

    Returns:
        DataFrame of all projected transactions
    """
    months = 13
    weeks = 53
    years = 1
    quarters = 4
    biweeks = 27

    # Create lookup dictionaries to avoid re-querying
    schedule_objects = {s.name: s for s in schedules}
    skip_objects = {s.name: s for s in skips}

    # Convert schedules to DataFrame
    if schedules:
        df = pd.DataFrame([{
            'name': s.name,
            'startdate': s.startdate.strftime('%Y-%m-%d') if s.startdate else None,
            'firstdate': s.firstdate.strftime('%Y-%m-%d') if s.firstdate else None,
            'frequency': s.frequency,
            'amount': s.amount,
            'type': s.type
        } for s in schedules])
    else:
        # Empty DataFrame if no schedules
        df = pd.DataFrame(columns=['name', 'startdate', 'firstdate', 'frequency', 'amount', 'type'])

    total_dict = {}

    # loop through the schedule and create transactions in a table out to the future number of years
    todaydate = datetime.today().date()
    for i in df.itertuples(index=False):
        format = '%Y-%m-%d'
        name = i.name
        startdate = i.startdate
        firstdate = i.firstdate
        frequency = i.frequency
        amount = i.amount
        type = i.type
        existing = schedule_objects.get(name)
        if not existing:
            continue  # Skip if schedule object not found
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
                    # Create a new row
                    new_row = {
                        'type': type,
                        'name': name,
                        'amount': amount,
                        'date': pd.tseries.offsets.BDay(1).rollback(rollbackdate).date()
                    }
                    # Append the row to the DataFrame
                    total_dict[len(total_dict)] = new_row
                else:
                    # Create a new row
                    new_row = {
                        'type': type,
                        'name': name,
                        'amount': amount,
                        'date': (futuredate - pd.tseries.offsets.BDay(0)).date()
                    }
                    # Append the row to the DataFrame
                    total_dict[len(total_dict)] = new_row
        elif frequency == 'Weekly':
            for k in range(weeks):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(weeks=k)
                if futuredate <= todaydate and datetime.today().weekday() < 5:
                    existing.startdate = futuredate + relativedelta(weeks=1)
                # Create a new row
                new_row = {
                    'type': type,
                    'name': name,
                    'amount': amount,
                    'date': (futuredate - pd.tseries.offsets.BDay(0)).date()
                }
                # Append the row to the DataFrame
                total_dict[len(total_dict)] = new_row
        elif frequency == 'Yearly':
            for k in range(years):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(years=k)
                if futuredate <= todaydate and datetime.today().weekday() < 5:
                    existing.startdate = futuredate + relativedelta(years=1)
                # Create a new row
                new_row = {
                    'type': type,
                    'name': name,
                    'amount': amount,
                    'date': (futuredate - pd.tseries.offsets.BDay(0)).date()
                }
                # Append the row to the DataFrame
                total_dict[len(total_dict)] = new_row
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
                # Create a new row
                new_row = {
                    'type': type,
                    'name': name,
                    'amount': amount,
                    'date': (futuredate - pd.tseries.offsets.BDay(0)).date()
                }
                # Append the row to the DataFrame
                total_dict[len(total_dict)] = new_row
        elif frequency == 'BiWeekly':
            for k in range(biweeks):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(weeks=2 * k)
                if futuredate <= todaydate and datetime.today().weekday() < 5:
                    existing.startdate = futuredate + relativedelta(weeks=2)
                # Create a new row
                new_row = {
                    'type': type,
                    'name': name,
                    'amount': amount,
                    'date': (futuredate - pd.tseries.offsets.BDay(0)).date()
                }
                # Append the row to the DataFrame
                total_dict[len(total_dict)] = new_row
        elif frequency == 'Onetime':
            futuredate = datetime.strptime(startdate, format).date()
            if futuredate < todaydate:
                db.session.delete(existing)
            else:
                # Create a new row
                new_row = {
                    'type': type,
                    'name': name,
                    'amount': amount,
                    'date': futuredate
                }
                # Append the row to the DataFrame
                total_dict[len(total_dict)] = new_row
    db.session.commit()

    # add the hold items
    for hold in holds:
        # Create a new row
        new_row = {
            'type': hold.type,
            'name': hold.name,
            'amount': hold.amount,
            'date': todaydate + relativedelta(days=1)
        }
        # Append the row to the DataFrame
        total_dict[len(total_dict)] = new_row

    # add the skip items
    for skip in skips:
        format = '%Y-%m-%d'
        skip_date = skip.date if isinstance(skip.date, date) else datetime.strptime(skip.date, format).date()

        if skip_date < todaydate:
            # Delete past skip items
            db.session.delete(skip)
        else:
            # Create a new row
            new_row = {
                'type': skip.type,
                'name': skip.name,
                'amount': skip.amount,
                'date': skip_date
            }
            # Append the row to the DataFrame
            total_dict[len(total_dict)] = new_row

    # Create DataFrame from total_dict
    if total_dict:
        total = pd.DataFrame.from_dict(total_dict, orient="index")
    else:
        # Return empty DataFrame with expected columns
        total = pd.DataFrame(columns=['type', 'name', 'amount', 'date'])

    return total


def calc_transactions(balance, total):
    # retrieve the total future transactions
    # Check if total DataFrame is empty
    if total.empty:
        # Return empty DataFrames if no transactions
        trans = pd.DataFrame(columns=['name', 'type', 'amount', 'date'])
        run_dict = {0: {'amount': balance, 'date': datetime.today().date()}}
        run = pd.DataFrame.from_dict(run_dict, orient="index")
        return trans, run

    df = total.sort_values(by="date", key=lambda x: np.argsort(index_natsorted(total["date"]))).reset_index(drop=True)
    trans_dict = {}
    # collect the next 60 days of transactions for the transactions table
    todaydate = datetime.today().date()
    todaydateplus = todaydate + relativedelta(months=2)
    for i in df.itertuples(index=False):
        if todaydateplus > \
                i.date > todaydate and "(SKIP)" not in i.name:
            # Create a new row from i[1]
            new_row = {
                'name': i.name,  # Accessing the 4th column value
                'type': i.type,
                'amount': i.amount,
                'date': i.date
            }
            # Append the row to the DataFrame
            trans_dict[len(trans_dict)] = new_row

    trans = pd.DataFrame.from_dict(trans_dict, orient="index")

    # for schedules marked as expenses, make the value negative for the sum
    # Create a copy to avoid modifying during iteration
    df = df.copy()
    for idx in df.index:
        if df.loc[idx, 'type'] == 'Expense':
            df.loc[idx, 'amount'] = float(df.loc[idx, 'amount']) * -1

    # group total transactions by date and sum the amounts for each date
    df = df.groupby("date")['amount'].sum().reset_index()

    # loop through the total transactions by date and add the sums to the total balance amount
    runbalance = balance
    run_dict = {}
    # Create a new row
    new_row = {
        'amount': runbalance,
        'date': datetime.today().date()
    }
    # Append the row to the DataFrame
    run_dict[len(run_dict)] = new_row
    for i in df.itertuples(index=False):
        rundate = i.date
        amount = i.amount
        if i.date > todaydate:
            runbalance += amount
            # Create a new row
            new_row = {
                'amount': runbalance,
                'date': rundate
            }
            # Append the row to the DataFrame
            run_dict[len(run_dict)] = new_row

    run = pd.DataFrame.from_dict(run_dict, orient="index")

    return trans, run


def plot_cash(run):
    # plot the running balances by date on a line plot
    df = run.sort_values(by='date', ascending=False)
    minbalance = df['amount'].min()
    minbalance = decimal.Decimal(str(minbalance)).quantize(decimal.Decimal('.01'))
    if float(minbalance) >= 0:
        minrange = 0
    else:
        minrange = float(minbalance) * 1.1
    maxbalance = 0
    todaydate = datetime.today().date()
    todaydateplus = todaydate + relativedelta(months=2)
    for i in df.itertuples(index=False):
        if todaydateplus > i.date > todaydate:
            if i.amount > maxbalance:
                maxbalance = i.amount
    maxrange = maxbalance * 1.1
    start_date = str(datetime.today().date())
    end_date = str(datetime.today().date() + relativedelta(months=2))
    layout = go.Layout(yaxis=dict(range=[minrange, maxrange]), xaxis=dict(range=[start_date, end_date]),
                       margin=dict(l=5, r=20, t=35, b=5), dragmode='pan')
    fig = go.Figure(data=go.Scatter(x=df['date'].values.tolist(), y=df['amount'].values.tolist(), mode='lines', line=dict(shape='spline', smoothing=0.8)))
    fig.update_layout(layout)
    fig.update_xaxes(title_text='Date')
    fig.update_yaxes(title_text='Amount')
    fig.update_layout(paper_bgcolor="PaleTurquoise")
    fig.update_layout(title="Cash Flow")
    fig.update_layout(xaxis_type='date')
    fig.update_layout(yaxis_tickformat='$,.2f')

    graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    return minbalance, graphJSON