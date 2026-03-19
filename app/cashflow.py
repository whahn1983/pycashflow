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


def update_cash(balance, schedules, holds, skips, scenarios=None):
    """
    Calculate cash flow with pre-filtered user data

    Args:
        balance: Current balance amount (Decimal)
        schedules: List of Schedule objects (pre-filtered for user)
        holds: List of Hold objects (pre-filtered for user)
        skips: List of Skip objects (pre-filtered for user)
        scenarios: List of Scenario objects (pre-filtered for user), optional

    Returns:
        trans: DataFrame of upcoming transactions
        run: DataFrame of running balance projections (schedules only)
        run_scenario: DataFrame of running balance projections (schedules + scenarios),
                      or None if no scenarios provided
    """
    total, total_scenario = calc_schedule(schedules, holds, skips, scenarios or [])

    trans, run = calc_transactions(balance, total)

    run_scenario = None
    if scenarios:
        _, run_scenario = calc_transactions(balance, total_scenario)

    return trans, run, run_scenario


def calc_schedule(schedules, holds, skips, scenarios=None):
    """
    Process schedules, holds, and skips into projected transactions.
    Also processes scenarios into a combined schedule+scenario projection.

    Args:
        schedules: List of Schedule objects (pre-filtered for user)
        holds: List of Hold objects (pre-filtered for user)
        skips: List of Skip objects (pre-filtered for user)
        scenarios: List of Scenario objects (pre-filtered for user), optional

    Returns:
        Tuple of (total, total_scenario) DataFrames:
            total: schedules + holds + skips only
            total_scenario: schedules + scenarios + holds + skips
    """
    if scenarios is None:
        scenarios = []

    months = 13
    weeks = 53
    years = 1
    quarters = 4
    biweeks = 27

    # Create lookup dictionaries to avoid re-querying
    schedule_objects = {s.name: s for s in schedules}
    scenario_objects = {s.name: s for s in scenarios}
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
        df = pd.DataFrame(columns=['name', 'startdate', 'firstdate', 'frequency', 'amount', 'type'])

    # Convert scenarios to DataFrame
    if scenarios:
        df_scenario = pd.DataFrame([{
            'name': s.name,
            'startdate': s.startdate.strftime('%Y-%m-%d') if s.startdate else None,
            'firstdate': s.firstdate.strftime('%Y-%m-%d') if s.firstdate else None,
            'frequency': s.frequency,
            'amount': s.amount,
            'type': s.type
        } for s in scenarios])
    else:
        df_scenario = pd.DataFrame(columns=['name', 'startdate', 'firstdate', 'frequency', 'amount', 'type'])

    total_dict = {}
    total_dict_scenario = {}

    # Loop through schedules — rows go into BOTH dicts
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
            continue
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
                    new_row = {
                        'type': type,
                        'name': name,
                        'amount': amount,
                        'date': pd.tseries.offsets.BDay(1).rollback(rollbackdate).date()
                    }
                    total_dict[len(total_dict)] = new_row
                    total_dict_scenario[len(total_dict_scenario)] = new_row
                else:
                    new_row = {
                        'type': type,
                        'name': name,
                        'amount': amount,
                        'date': (futuredate - pd.tseries.offsets.BDay(0)).date()
                    }
                    total_dict[len(total_dict)] = new_row
                    total_dict_scenario[len(total_dict_scenario)] = new_row
        elif frequency == 'Weekly':
            for k in range(weeks):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(weeks=k)
                if futuredate <= todaydate and datetime.today().weekday() < 5:
                    existing.startdate = futuredate + relativedelta(weeks=1)
                new_row = {
                    'type': type,
                    'name': name,
                    'amount': amount,
                    'date': (futuredate - pd.tseries.offsets.BDay(0)).date()
                }
                total_dict[len(total_dict)] = new_row
                total_dict_scenario[len(total_dict_scenario)] = new_row
        elif frequency == 'Yearly':
            for k in range(years):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(years=k)
                if futuredate <= todaydate and datetime.today().weekday() < 5:
                    existing.startdate = futuredate + relativedelta(years=1)
                new_row = {
                    'type': type,
                    'name': name,
                    'amount': amount,
                    'date': (futuredate - pd.tseries.offsets.BDay(0)).date()
                }
                total_dict[len(total_dict)] = new_row
                total_dict_scenario[len(total_dict_scenario)] = new_row
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
                new_row = {
                    'type': type,
                    'name': name,
                    'amount': amount,
                    'date': (futuredate - pd.tseries.offsets.BDay(0)).date()
                }
                total_dict[len(total_dict)] = new_row
                total_dict_scenario[len(total_dict_scenario)] = new_row
        elif frequency == 'BiWeekly':
            for k in range(biweeks):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(weeks=2 * k)
                if futuredate <= todaydate and datetime.today().weekday() < 5:
                    existing.startdate = futuredate + relativedelta(weeks=2)
                new_row = {
                    'type': type,
                    'name': name,
                    'amount': amount,
                    'date': (futuredate - pd.tseries.offsets.BDay(0)).date()
                }
                total_dict[len(total_dict)] = new_row
                total_dict_scenario[len(total_dict_scenario)] = new_row
        elif frequency == 'Onetime':
            futuredate = datetime.strptime(startdate, format).date()
            if futuredate < todaydate:
                db.session.delete(existing)
            else:
                new_row = {
                    'type': type,
                    'name': name,
                    'amount': amount,
                    'date': futuredate
                }
                total_dict[len(total_dict)] = new_row
                total_dict_scenario[len(total_dict_scenario)] = new_row
    db.session.commit()

    # Loop through scenarios — rows go into total_dict_scenario ONLY.
    # Onetime scenarios are NOT auto-deleted when past (user removes them manually).
    for i in df_scenario.itertuples(index=False):
        format = '%Y-%m-%d'
        name = i.name
        startdate = i.startdate
        firstdate = i.firstdate
        frequency = i.frequency
        amount = i.amount
        type = i.type
        existing = scenario_objects.get(name)
        if not existing:
            continue
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
                    new_row = {
                        'type': type,
                        'name': name,
                        'amount': amount,
                        'date': pd.tseries.offsets.BDay(1).rollback(rollbackdate).date()
                    }
                    total_dict_scenario[len(total_dict_scenario)] = new_row
                else:
                    new_row = {
                        'type': type,
                        'name': name,
                        'amount': amount,
                        'date': (futuredate - pd.tseries.offsets.BDay(0)).date()
                    }
                    total_dict_scenario[len(total_dict_scenario)] = new_row
        elif frequency == 'Weekly':
            for k in range(weeks):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(weeks=k)
                if futuredate <= todaydate and datetime.today().weekday() < 5:
                    existing.startdate = futuredate + relativedelta(weeks=1)
                new_row = {
                    'type': type,
                    'name': name,
                    'amount': amount,
                    'date': (futuredate - pd.tseries.offsets.BDay(0)).date()
                }
                total_dict_scenario[len(total_dict_scenario)] = new_row
        elif frequency == 'Yearly':
            for k in range(years):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(years=k)
                if futuredate <= todaydate and datetime.today().weekday() < 5:
                    existing.startdate = futuredate + relativedelta(years=1)
                new_row = {
                    'type': type,
                    'name': name,
                    'amount': amount,
                    'date': (futuredate - pd.tseries.offsets.BDay(0)).date()
                }
                total_dict_scenario[len(total_dict_scenario)] = new_row
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
                new_row = {
                    'type': type,
                    'name': name,
                    'amount': amount,
                    'date': (futuredate - pd.tseries.offsets.BDay(0)).date()
                }
                total_dict_scenario[len(total_dict_scenario)] = new_row
        elif frequency == 'BiWeekly':
            for k in range(biweeks):
                futuredate = datetime.strptime(startdate, format).date() + relativedelta(weeks=2 * k)
                if futuredate <= todaydate and datetime.today().weekday() < 5:
                    existing.startdate = futuredate + relativedelta(weeks=2)
                new_row = {
                    'type': type,
                    'name': name,
                    'amount': amount,
                    'date': (futuredate - pd.tseries.offsets.BDay(0)).date()
                }
                total_dict_scenario[len(total_dict_scenario)] = new_row
        elif frequency == 'Onetime':
            futuredate = datetime.strptime(startdate, format).date()
            # Past Onetime scenarios are skipped in projection but NOT deleted
            if futuredate >= todaydate:
                new_row = {
                    'type': type,
                    'name': name,
                    'amount': amount,
                    'date': futuredate
                }
                total_dict_scenario[len(total_dict_scenario)] = new_row
    db.session.commit()

    # Add holds to BOTH dicts
    for hold in holds:
        new_row = {
            'type': hold.type,
            'name': hold.name,
            'amount': hold.amount,
            'date': todaydate + relativedelta(days=1)
        }
        total_dict[len(total_dict)] = new_row
        total_dict_scenario[len(total_dict_scenario)] = new_row

    # Add skips to BOTH dicts
    for skip in skips:
        format = '%Y-%m-%d'
        skip_date = skip.date if isinstance(skip.date, date) else datetime.strptime(skip.date, format).date()

        if skip_date < todaydate:
            db.session.delete(skip)
        else:
            new_row = {
                'type': skip.type,
                'name': skip.name,
                'amount': skip.amount,
                'date': skip_date
            }
            total_dict[len(total_dict)] = new_row
            total_dict_scenario[len(total_dict_scenario)] = new_row
    db.session.commit()

    total = pd.DataFrame.from_dict(total_dict, orient="index") if total_dict else pd.DataFrame(columns=['type', 'name', 'amount', 'date'])
    total_scenario = pd.DataFrame.from_dict(total_dict_scenario, orient="index") if total_dict_scenario else pd.DataFrame(columns=['type', 'name', 'amount', 'date'])

    return total, total_scenario


def calc_transactions(balance, total):
    # retrieve the total future transactions
    if total.empty:
        trans = pd.DataFrame(columns=['name', 'type', 'amount', 'date'])
        run_dict = {0: {'amount': float(balance), 'date': datetime.today().date()}}
        run = pd.DataFrame.from_dict(run_dict, orient="index")
        return trans, run

    df = total.sort_values(by="date", key=lambda x: np.argsort(index_natsorted(total["date"]))).reset_index(drop=True)
    trans_dict = {}
    todaydate = datetime.today().date()
    todaydateplus = todaydate + relativedelta(months=2)
    for i in df.itertuples(index=False):
        if todaydateplus > \
                i.date > todaydate and "(SKIP)" not in i.name:
            new_row = {
                'name': i.name,
                'type': i.type,
                'amount': i.amount,
                'date': i.date
            }
            trans_dict[len(trans_dict)] = new_row

    trans = pd.DataFrame.from_dict(trans_dict, orient="index")

    df = df.copy()
    df['amount'] = df['amount'].astype(float)
    for idx in df.index:
        if df.loc[idx, 'type'] == 'Expense':
            df.loc[idx, 'amount'] = df.loc[idx, 'amount'] * -1

    df = df.groupby("date")['amount'].sum().reset_index()

    runbalance = float(balance)
    run_dict = {}
    new_row = {
        'amount': runbalance,
        'date': datetime.today().date()
    }
    run_dict[len(run_dict)] = new_row
    for i in df.itertuples(index=False):
        rundate = i.date
        amount = i.amount
        if i.date > todaydate:
            runbalance += amount
            new_row = {
                'amount': runbalance,
                'date': rundate
            }
            run_dict[len(run_dict)] = new_row

    run = pd.DataFrame.from_dict(run_dict, orient="index")

    return trans, run


def calculate_cash_risk_score(balance, run):
    """
    Calculate a 0-100 cash risk score (higher = safer).

    Factors and weights:
        40% runway score        — current_balance / avg_daily_expense
        25% lowest balance score — lowest_projected_balance / avg_monthly_expense
        20% days-to-lowest score — days until the lowest balance occurs
        15% volatility score     — spread of balance over the projection

    Returns a dict with: score, status, color, runway_days,
    lowest_balance, days_to_lowest, avg_daily_expense.
    """
    todaydate = datetime.today().date()
    current_balance = float(balance)

    if run.empty or len(run) < 2 or current_balance <= 0:
        return {
            'score': 50,
            'status': 'Watch',
            'color': 'yellow',
            'runway_days': 0,
            'lowest_balance': current_balance,
            'days_to_lowest': 0,
            'avg_daily_expense': 0,
        }

    run_copy = run.copy()
    run_copy['amount'] = run_copy['amount'].astype(float)
    run_copy['date_val'] = run_copy['date'].apply(
        lambda d: d if hasattr(d, 'year') else datetime.strptime(str(d), '%Y-%m-%d').date()
    )
    run_copy = run_copy.sort_values('date_val').reset_index(drop=True)

    # Lowest balance and when it occurs
    min_idx = run_copy['amount'].idxmin()
    lowest_balance = float(run_copy.loc[min_idx, 'amount'])
    lowest_date = run_copy.loc[min_idx, 'date_val']
    days_to_lowest = max(0, (lowest_date - todaydate).days)

    # Max balance for volatility
    max_balance = float(run_copy['amount'].max())

    # Average daily expense from negative balance changes over the full projection
    amounts = run_copy['amount'].values
    total_days = max(1, (run_copy['date_val'].iloc[-1] - run_copy['date_val'].iloc[0]).days)
    expense_total = sum(
        abs(amounts[i] - amounts[i - 1])
        for i in range(1, len(amounts))
        if amounts[i] < amounts[i - 1]
    )
    avg_daily_expense = expense_total / total_days if total_days > 0 else 1.0
    if avg_daily_expense == 0:
        avg_daily_expense = 1.0

    avg_monthly_expense = avg_daily_expense * 30
    cash_runway_days = current_balance / avg_daily_expense

    # --- Component scores (0-100, higher = safer) ---

    # 1. Runway score (40%)
    if cash_runway_days >= 90:
        runway_score = 100.0
    elif cash_runway_days >= 45:
        runway_score = 40.0 + (cash_runway_days - 45.0) * (60.0 / 45.0)
    else:
        runway_score = max(0.0, cash_runway_days * (40.0 / 45.0))

    # 2. Lowest balance score (25%)
    ratio = lowest_balance / avg_monthly_expense if avg_monthly_expense > 0 else 1.0
    lowest_score = max(0.0, min(100.0, ratio * 100.0))

    # 3. Days-to-lowest score (20%)
    if days_to_lowest >= 30:
        days_score = 100.0
    elif days_to_lowest >= 14:
        days_score = 40.0 + (days_to_lowest - 14.0) * (60.0 / 16.0)
    else:
        days_score = max(0.0, days_to_lowest * (40.0 / 14.0))

    # 4. Volatility score (15%)
    volatility = max_balance - lowest_balance
    vol_ratio = volatility / current_balance if current_balance > 0 else 1.0
    if vol_ratio <= 0.5:
        vol_score = 100.0
    elif vol_ratio <= 2.0:
        vol_score = max(0.0, 100.0 - ((vol_ratio - 0.5) / 1.5) * 100.0)
    else:
        vol_score = 0.0

    # Weighted composite
    score = (
        runway_score * 0.40 +
        lowest_score * 0.25 +
        days_score * 0.20 +
        vol_score * 0.15
    )
    score = int(max(0, min(100, round(score))))

    if score >= 80:
        status, color = 'Safe', 'green'
    elif score >= 60:
        status, color = 'Stable', 'blue'
    elif score >= 40:
        status, color = 'Watch', 'yellow'
    elif score >= 20:
        status, color = 'Risk', 'orange'
    else:
        status, color = 'Critical', 'red'

    return {
        'score': score,
        'status': status,
        'color': color,
        'runway_days': round(cash_runway_days, 1),
        'lowest_balance': round(lowest_balance, 2),
        'days_to_lowest': days_to_lowest,
        'avg_daily_expense': round(avg_daily_expense, 2),
    }


def plot_cash(run, run_scenario=None):
    # plot the running balances by date on a line plot
    # Schedule-only line
    df = run.sort_values(by='date', ascending=False)
    df['amount'] = df['amount'].astype(float)
    minbalance = df['amount'].min()
    minbalance = decimal.Decimal(str(minbalance)).quantize(decimal.Decimal('.01'))

    todaydate = datetime.today().date()
    todaydateplus = todaydate + relativedelta(months=2)

    if float(minbalance) >= 0:
        minrange = 0.0
    else:
        minrange = float(minbalance) * 1.1

    maxbalance = 0.0
    for i in df.itertuples(index=False):
        if todaydateplus > i.date > todaydate:
            if i.amount > maxbalance:
                maxbalance = i.amount

    # Scenario line setup
    min_scenario = None
    df_s = None
    if run_scenario is not None:
        df_s = run_scenario.sort_values(by='date', ascending=False)
        df_s['amount'] = df_s['amount'].astype(float)
        scenario_min = df_s['amount'].min()
        min_scenario = decimal.Decimal(str(scenario_min)).quantize(decimal.Decimal('.01'))

        # Expand y-axis range to fit both lines
        if float(min_scenario) < minrange:
            minrange = float(min_scenario) * 1.1 if float(min_scenario) < 0 else minrange
        for i in df_s.itertuples(index=False):
            if todaydateplus > i.date > todaydate:
                if i.amount > maxbalance:
                    maxbalance = i.amount

    maxrange = maxbalance * 1.1

    start_date = str(todaydate)
    end_date = str(todaydate + relativedelta(months=2))

    layout = go.Layout(
        yaxis=dict(range=[minrange, maxrange]),
        xaxis=dict(range=[start_date, end_date]),
        margin=dict(l=0, r=0, t=0, b=0),
        dragmode='pan',
        showlegend=(run_scenario is not None),
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1,
            font=dict(color='#cbd5e1')
        )
    )

    traces = []

    if df_s is not None:
        traces.append(
            go.Scatter(
                name='With Scenarios',
                x=df_s['date'].values.tolist(),
                y=df_s['amount'].values.tolist(),
                mode='lines',
                line=dict(shape='spline', smoothing=0.8, color='#f59e0b', dash='dash')
            )
        )

    traces.append(
        go.Scatter(
            name='Schedule',
            x=df['date'].values.tolist(),
            y=df['amount'].values.tolist(),
            mode='lines',
            line=dict(shape='spline', smoothing=0.8, color='#3b82f6')
        )
    )

    fig = go.Figure(data=traces)
    fig.update_layout(layout)
    fig.update_layout(paper_bgcolor="PaleTurquoise")
    fig.update_layout(xaxis_type='date')
    fig.update_layout(yaxis_tickformat='$,.0f')

    graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    return minbalance, min_scenario, graphJSON
