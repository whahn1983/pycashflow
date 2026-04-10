from app import db
from .models import Schedule, Skip
from datetime import datetime, date, timedelta
import pandas as pd
import json
import plotly
import os
from dateutil.relativedelta import relativedelta
from natsort import index_natsorted
import numpy as np
import decimal
import plotly.graph_objs as go


def update_cash(balance, schedules, holds, skips, scenarios=None, commit=True):
    """
    Calculate cash flow with pre-filtered user data

    Args:
        balance: Current balance amount (Decimal)
        schedules: List of Schedule objects (pre-filtered for user)
        holds: List of Hold objects (pre-filtered for user)
        skips: List of Skip objects (pre-filtered for user)
        scenarios: List of Scenario objects (pre-filtered for user), optional
        commit: If True (default), persist housekeeping changes (date advances,
                one-time deletions) to the database.  Pass False for read-only
                callers such as GET API endpoints.

    Returns:
        trans: DataFrame of upcoming transactions
        run: DataFrame of running balance projections (schedules only)
        run_scenario: DataFrame of running balance projections (schedules + scenarios),
                      or None if no scenarios provided
    """
    total, total_scenario = calc_schedule(schedules, holds, skips, scenarios or [], commit=commit)

    trans, run = calc_transactions(balance, total)

    run_scenario = None
    if scenarios:
        _, run_scenario = calc_transactions(balance, total_scenario)

    return trans, run, run_scenario


def calc_schedule(schedules, holds, skips, scenarios=None, commit=True):
    """
    Process schedules, holds, and skips into projected transactions.
    Also processes scenarios into a combined schedule+scenario projection.

    Args:
        schedules: List of Schedule objects (pre-filtered for user)
        holds: List of Hold objects (pre-filtered for user)
        skips: List of Skip objects (pre-filtered for user)
        scenarios: List of Scenario objects (pre-filtered for user), optional
        commit: If True (default), persist housekeeping changes to the database.

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
            firstdate_val = datetime.strptime(startdate, format).date()
            if commit:
                existing.firstdate = firstdate_val
                db.session.commit()
            firstdate = firstdate_val.strftime(format)
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
                    if commit:
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
                    if commit:
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
                    if commit:
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
                    if commit:
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
                    if commit:
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
                if commit:
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
    if commit:
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
            firstdate_val = datetime.strptime(startdate, format).date()
            if commit:
                existing.firstdate = firstdate_val
                db.session.commit()
            firstdate = firstdate_val.strftime(format)
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
                    if commit:
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
                    if commit:
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
                    if commit:
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
                    if commit:
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
                    if commit:
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
    if commit:
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
            if commit:
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
    if commit:
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
    todaydateplus = todaydate + timedelta(days=90)
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

    Evaluates actual projected liquidity risk over the forecast path rather than
    relying on naive runway math (current_balance / avg_daily_expense). This
    prevents over-penalising businesses with healthy cyclical cash flows (e.g.
    monthly income arriving near month-end) that show a short naive runway but
    never actually dip into a dangerous liquidity position.

    Factors and weights:
        35% min_balance_ratio    — lowest_projected_balance / avg_monthly_expense
        25% days_below_threshold — % of horizon days where balance < 1 month of expenses
        20% recovery_speed       — days to recover above threshold after the lowest point
        20% near_term_buffer     — minimum balance over the next 14 days

    Runway (current_balance / avg_daily_expense) is retained as an informational
    output field but is no longer a primary scoring input.

    Returns a dict with: score, status, color, runway_days,
    lowest_balance, days_to_lowest, avg_daily_expense.
    """
    todaydate = datetime.today().date()
    current_balance = float(balance)

    if current_balance <= 0:
        return {
            'score': 0,
            'status': 'Critical',
            'color': 'red',
            'runway_days': 0,
            'lowest_balance': current_balance,
            'days_to_lowest': 0,
            'avg_daily_expense': 0,
            'days_below_threshold': 0,
            'pct_below_threshold': 0.0,
            'recovery_days': None,
            'near_term_buffer': current_balance,
        }

    if run.empty:
        return {
            'score': 50,
            'status': 'Watch',
            'color': 'yellow',
            'runway_days': 0,
            'lowest_balance': current_balance,
            'days_to_lowest': 0,
            'avg_daily_expense': 0,
            'days_below_threshold': 0,
            'pct_below_threshold': 0.0,
            'recovery_days': None,
            'near_term_buffer': current_balance,
        }

    if len(run) == 1:
        # Single checkpoint: derive actual risk factors from the lone projection row
        # rather than hard-coding safe-looking defaults that mask cash-negative events.
        single_row = run.iloc[0]
        single_balance = float(single_row['amount'])
        single_date = (
            single_row['date'] if hasattr(single_row['date'], 'year')
            else datetime.strptime(str(single_row['date']), '%Y-%m-%d').date()
        )
        days_to_row = max(0, (single_date - todaydate).days)

        lowest_balance = min(current_balance, single_balance)
        days_to_lowest = days_to_row if single_balance < current_balance else 0

        # near_term_buffer: minimum balance over the 14-day window.
        # For a row within 14 days the account stays at current_balance until that date,
        # so use the minimum of the two to avoid overstating short-term liquidity.
        near_term_buffer = min(current_balance, single_balance) if days_to_row <= 14 else current_balance

        # Rough daily expense from balance delta.
        # When balance_delta <= 0 (income-only or flat row) there are no observable
        # expenses, so avg_daily_expense stays 0 (used by ai_insights to emit
        # min_balance_ratio=None rather than a fabricated large value).
        # Runway is calculated independently: stable/improving balance means indefinite
        # runway, represented as float('inf') so templates can show it correctly.
        balance_delta = current_balance - single_balance
        avg_daily_expense = balance_delta / max(1, days_to_row) if balance_delta > 0 else 0
        if avg_daily_expense > 0:
            cash_runway_days: float | None = current_balance / avg_daily_expense
        else:
            # No observable expense drain: runway is effectively infinite; use None
            # so templates can display a human-friendly label instead of "inf".
            cash_runway_days = None

        # days_below_threshold: count remaining horizon days when balance goes negative
        horizon_days = 90
        if single_balance < 0:
            days_below = max(0, horizon_days - days_to_row)
            pct_below = days_below / horizon_days
            score, status, color = 0, 'Critical', 'red'
        else:
            days_below = 0
            pct_below = 0.0
            score, status, color = 50, 'Watch', 'yellow'

        return {
            'score': score,
            'status': status,
            'color': color,
            'runway_days': round(cash_runway_days, 1) if cash_runway_days is not None else None,
            'lowest_balance': round(lowest_balance, 2),
            'days_to_lowest': days_to_lowest,
            'avg_daily_expense': round(avg_daily_expense, 2),
            'days_below_threshold': days_below,
            'pct_below_threshold': round(pct_below, 4),
            'recovery_days': None,
            'near_term_buffer': round(near_term_buffer, 2),
        }

    run_copy = run.copy()
    run_copy['amount'] = run_copy['amount'].astype(float)
    run_copy['date_val'] = run_copy['date'].apply(
        lambda d: d if hasattr(d, 'year') else datetime.strptime(str(d), '%Y-%m-%d').date()
    )
    run_copy = run_copy.sort_values('date_val').reset_index(drop=True)

    # Scope primary calculations to 90-day window
    horizon = todaydate + timedelta(days=90)
    run_90 = run_copy[run_copy['date_val'] <= horizon].reset_index(drop=True)
    if run_90.empty:
        run_90 = run_copy.reset_index(drop=True)

    # Near-term window for the 14-day buffer factor
    near_term_horizon = todaydate + timedelta(days=14)
    run_14 = run_copy[run_copy['date_val'] <= near_term_horizon]

    # Lowest balance and when it occurs (within 90-day window)
    min_idx = run_90['amount'].idxmin()
    lowest_balance = float(run_90.loc[min_idx, 'amount'])
    lowest_date = run_90.loc[min_idx, 'date_val']
    days_to_lowest = max(0, (lowest_date - todaydate).days)

    # Average daily expense: sum of all downward balance moves divided by horizon days.
    # Only negative changes count so that income events do not distort the expense rate.
    amounts = run_90['amount'].values
    total_days = max(1, (run_90['date_val'].iloc[-1] - run_90['date_val'].iloc[0]).days)
    expense_total = sum(
        abs(amounts[i] - amounts[i - 1])
        for i in range(1, len(amounts))
        if amounts[i] < amounts[i - 1]
    )
    avg_daily_expense = expense_total / total_days if total_days > 0 else 1.0
    if avg_daily_expense == 0:
        avg_daily_expense = 1.0

    avg_monthly_expense = avg_daily_expense * 30

    # Runway kept as informational output only (not used in scoring below)
    cash_runway_days = current_balance / avg_daily_expense

    # Liquidity threshold: one month of average expenses.
    # A balance above this level is considered adequately liquid.
    liquidity_threshold = avg_monthly_expense

    # --- Component scores (0–100, higher = safer) ---

    # 1. Minimum balance ratio (35%)
    # Answers: "Does the balance ever fall dangerously low relative to monthly expenses?"
    # A ratio >= 1.5 means the worst-case balance covers 1.5 months of expenses — very healthy.
    # This factor directly fixes the cyclical-income problem: a business whose balance briefly
    # dips mid-month but whose lowest point still covers >1 month of expenses is rated safely.
    ratio = lowest_balance / avg_monthly_expense if avg_monthly_expense > 0 else 1.0
    if ratio >= 1.5:
        min_balance_score = 100.0
    elif ratio >= 1.0:
        # Strong: between 1 and 1.5 months of cover
        min_balance_score = 75.0 + (ratio - 1.0) / 0.5 * 25.0
    elif ratio >= 0.5:
        # Moderate: between half and one month of cover
        min_balance_score = 40.0 + (ratio - 0.5) / 0.5 * 35.0
    elif ratio >= 0.0:
        # Weak: less than half a month of cover but still positive
        min_balance_score = ratio / 0.5 * 40.0
    else:
        # Balance goes negative — critical
        min_balance_score = 0.0

    # 2. Days below liquidity threshold (25%)
    # Answers: "How much of the forecast period is spent in a low-cash state?"
    # A one-day dip (e.g. income arrives the day after expenses) is very different from
    # spending 30% of the horizon below threshold. This factor captures that distinction.
    days_below = 0
    for i in range(len(run_90)):
        if float(run_90.loc[i, 'amount']) < liquidity_threshold:
            if i < len(run_90) - 1:
                seg_days = (run_90.loc[i + 1, 'date_val'] - run_90.loc[i, 'date_val']).days
            else:
                # Last checkpoint: count remaining days to the end of the 90-day horizon
                seg_days = max(0, (horizon - run_90.loc[i, 'date_val']).days)
            days_below += max(0, seg_days)

    horizon_days = 90
    pct_below = days_below / horizon_days
    # Linear: 0% of horizon below threshold → 100; 50%+ → 0
    days_below_score = max(0.0, 100.0 - (pct_below / 0.5) * 100.0)

    # 3. Recovery speed (20%)
    # Answers: "After the worst-case low, how quickly does cash recover above the threshold?"
    # Fast recovery (e.g. payroll income arriving soon after month-end) signals a healthy
    # cyclical pattern. Slow or absent recovery signals sustained structural risk.
    recovery_days_val = None  # None = never recovered; 0 = threshold never breached
    if lowest_balance >= liquidity_threshold:
        # Balance never fell below threshold — no recovery needed
        recovery_score = 100.0
        recovery_days_val = 0
    else:
        post_low = run_90[run_90['date_val'] >= lowest_date]
        recovered = post_low[post_low['amount'] >= liquidity_threshold]
        if not recovered.empty:
            recovery_date = recovered.iloc[0]['date_val']
            recovery_days = max(0, (recovery_date - lowest_date).days)
            recovery_days_val = recovery_days
            if recovery_days <= 7:
                # Very fast (≤1 week): near-perfect score
                recovery_score = 90.0 + (7 - recovery_days) / 7.0 * 10.0
            elif recovery_days <= 30:
                # Moderate (1 week – 1 month): linear 50–90
                recovery_score = 50.0 + (30 - recovery_days) / 23.0 * 40.0
            else:
                # Slow (>1 month): linear 0–50
                recovery_score = max(0.0, 50.0 - (recovery_days - 30) / 60.0 * 50.0)
        else:
            # No recovery within the 90-day horizon — major risk signal
            recovery_score = 0.0

    # 4. Near-term liquidity buffer (14 days) (20%)
    # Answers: "Is there an imminent cash shortfall in the next two weeks?"
    # Imminent dips should be penalised more heavily than distant ones.
    # If no transactions fall within 14 days, current_balance is used (no change expected).
    near_term_min = float(run_14['amount'].min()) if not run_14.empty else current_balance
    nt_ratio = near_term_min / avg_monthly_expense if avg_monthly_expense > 0 else 1.0
    if nt_ratio >= 1.5:
        near_term_score = 100.0
    elif nt_ratio >= 1.0:
        near_term_score = 75.0 + (nt_ratio - 1.0) / 0.5 * 25.0
    elif nt_ratio >= 0.5:
        near_term_score = 40.0 + (nt_ratio - 0.5) / 0.5 * 35.0
    elif nt_ratio >= 0.0:
        near_term_score = nt_ratio / 0.5 * 40.0
    else:
        near_term_score = 0.0

    # Weighted composite
    score = (
        min_balance_score * 0.35 +
        days_below_score  * 0.25 +
        recovery_score    * 0.20 +
        near_term_score   * 0.20
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
        'days_below_threshold': days_below,
        'pct_below_threshold': round(pct_below, 4),
        'recovery_days': recovery_days_val,
        'near_term_buffer': round(near_term_min, 2),
    }


def plot_cash(run, run_scenario=None):
    # plot the running balances by date on a line plot
    # Schedule-only line
    df = run.sort_values(by='date', ascending=False)
    df['amount'] = df['amount'].astype(float)
    todaydate = datetime.today().date()
    horizon_90 = todaydate + timedelta(days=90)
    df_90 = df[df['date'] <= horizon_90]
    minbalance = df_90['amount'].min() if not df_90.empty else df['amount'].min()
    minbalance = decimal.Decimal(str(minbalance)).quantize(decimal.Decimal('.01'))

    todaydateplus = todaydate + timedelta(days=90)

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
        df_s_90 = df_s[df_s['date'] <= horizon_90]
        scenario_min = df_s_90['amount'].min() if not df_s_90.empty else df_s['amount'].min()
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
    end_date = str(todaydate + timedelta(days=90))

    layout = go.Layout(
        yaxis=dict(range=[minrange, maxrange]),
        xaxis=dict(range=[start_date, end_date]),
        margin=dict(l=0, r=0, t=0, b=0),
        dragmode='pan',
        clickmode='event',
        hovermode='closest',
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
                hovertemplate='%{x|%b %d, %Y}<br>$%{y:,.2f}<extra>With Scenarios</extra>',
                line=dict(shape='spline', smoothing=0.8, color='#f59e0b', dash='dash')
            )
        )

    traces.append(
        go.Scatter(
            name='Schedule',
            x=df['date'].values.tolist(),
            y=df['amount'].values.tolist(),
            mode='lines',
            hovertemplate='%{x|%b %d, %Y}<br>$%{y:,.2f}<extra>Schedule</extra>',
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
