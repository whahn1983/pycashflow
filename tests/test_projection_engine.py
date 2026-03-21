"""
Tests for the core cash flow projection engine.

Focuses on calc_transactions() — the pure, stateless function that converts
a flat list of scheduled transactions + a starting balance into:
  - trans: the upcoming transactions visible in the 90-day window
  - run:   the running balance over time

calc_transactions has no database dependencies and is ideal for unit testing.

calc_schedule() and update_cash() touch the database session (for date-advance
bookkeeping), so tests for those functions use the ``app_ctx`` fixture provided
by conftest.py to run inside a real Flask application context backed by an
in-memory SQLite database.
"""

import types
from datetime import date, timedelta

import pandas as pd
import pytest

# conftest.py imports _helpers before any test module is collected, so the names
# below are always bound to the real implementations even if test_cash_risk_score.py
# later replaces sys.modules['app.cashflow'] with a stub.
from _helpers import calc_transactions, calc_schedule, update_cash


# ── Helpers ───────────────────────────────────────────────────────────────────

def future(days: int) -> date:
    """Return a date N days from today."""
    return date.today() + timedelta(days=days)


def make_total(*rows) -> pd.DataFrame:
    """
    Build a minimal 'total' DataFrame from keyword dicts.
    Each dict must have: type, name, amount, date (a date object).
    """
    return pd.DataFrame(list(rows))


def make_schedule_obj(name, amount, frequency, days_offset=30, type_="Income"):
    """
    Create a SimpleNamespace that mimics a Schedule ORM object.

    Using a future start date ensures that the date-advance / delete code paths
    inside calc_schedule() are never triggered, so no real ORM object is needed
    and db.session.commit() is a safe no-op.
    """
    start = future(days_offset)
    return types.SimpleNamespace(
        name=name,
        amount=amount,
        frequency=frequency,
        startdate=start,
        firstdate=start,
        type=type_,
    )


# ── Tests: empty / minimal input ─────────────────────────────────────────────


class TestEmptyInput:
    def test_empty_total_returns_empty_trans(self):
        total = pd.DataFrame(columns=["type", "name", "amount", "date"])
        trans, run = calc_transactions(5000.0, total)
        assert trans.empty

    def test_empty_total_run_starts_with_current_balance(self):
        total = pd.DataFrame(columns=["type", "name", "amount", "date"])
        _, run = calc_transactions(5000.0, total)
        assert len(run) == 1
        assert float(run["amount"].iloc[0]) == pytest.approx(5000.0)

    def test_empty_total_run_date_is_today(self):
        total = pd.DataFrame(columns=["type", "name", "amount", "date"])
        _, run = calc_transactions(5000.0, total)
        row_date = run["date"].iloc[0]
        if hasattr(row_date, "date"):
            row_date = row_date.date()
        assert row_date == date.today()


# ── Tests: income transactions ───────────────────────────────────────────────


class TestIncomeTransactions:
    def test_future_income_increases_balance(self):
        total = make_total(
            {"type": "Income", "name": "Salary", "amount": 3000.0, "date": future(15)}
        )
        _, run = calc_transactions(5000.0, total)
        end = float(run["amount"].iloc[-1])
        assert end == pytest.approx(8000.0)

    def test_income_within_90_days_appears_in_trans(self):
        total = make_total(
            {"type": "Income", "name": "Salary", "amount": 3000.0, "date": future(15)}
        )
        trans, _ = calc_transactions(5000.0, total)
        assert not trans.empty
        assert "Salary" in trans["name"].values

    def test_income_outside_90_days_absent_from_trans(self):
        """Transactions beyond the 90-day window must not appear in trans."""
        total = make_total(
            {"type": "Income", "name": "FarFuture", "amount": 1000.0, "date": future(95)}
        )
        trans, _ = calc_transactions(5000.0, total)
        assert trans.empty

    def test_income_outside_90_days_still_affects_run_balance(self):
        """The run balance includes all future transactions, not just 90-day ones."""
        total = make_total(
            {"type": "Income", "name": "FarFuture", "amount": 1000.0, "date": future(95)}
        )
        _, run = calc_transactions(5000.0, total)
        assert float(run["amount"].iloc[-1]) == pytest.approx(6000.0)


# ── Tests: expense transactions ──────────────────────────────────────────────


class TestExpenseTransactions:
    def test_future_expense_decreases_balance(self):
        total = make_total(
            {"type": "Expense", "name": "Rent", "amount": 1000.0, "date": future(10)}
        )
        _, run = calc_transactions(5000.0, total)
        end = float(run["amount"].iloc[-1])
        assert end == pytest.approx(4000.0)

    def test_expense_within_90_days_appears_in_trans(self):
        total = make_total(
            {"type": "Expense", "name": "Rent", "amount": 1000.0, "date": future(10)}
        )
        trans, _ = calc_transactions(5000.0, total)
        assert not trans.empty
        assert "Rent" in trans["name"].values

    def test_expense_amount_in_trans_is_positive(self):
        """trans amounts are stored as positive; the type column signals direction."""
        total = make_total(
            {"type": "Expense", "name": "Rent", "amount": 1000.0, "date": future(10)}
        )
        trans, _ = calc_transactions(5000.0, total)
        assert float(trans["amount"].iloc[0]) > 0


# ── Tests: balance accumulation order ────────────────────────────────────────


class TestBalanceAccumulation:
    def test_expense_before_income_causes_dip_then_rise(self):
        """
        Expense on day 10, income on day 20.
        The balance should dip after day 10 then rise after day 20.
        """
        total = make_total(
            {"type": "Expense", "name": "Rent", "amount": 1000.0, "date": future(10)},
            {"type": "Income", "name": "Salary", "amount": 3000.0, "date": future(20)},
        )
        _, run = calc_transactions(5000.0, total)
        run_sorted = run.copy()
        run_sorted["_d"] = run_sorted["date"].apply(
            lambda d: d.date() if hasattr(d, "date") else d
        )
        run_sorted = run_sorted.sort_values("_d").reset_index(drop=True)

        assert float(run_sorted["amount"].iloc[0]) == pytest.approx(5000.0)
        assert float(run_sorted["amount"].iloc[1]) == pytest.approx(4000.0)
        assert float(run_sorted["amount"].iloc[-1]) == pytest.approx(7000.0)

    def test_income_before_expense_no_dip(self):
        """Income on day 5, expense on day 15 — balance rises then falls."""
        total = make_total(
            {"type": "Income", "name": "Salary", "amount": 3000.0, "date": future(5)},
            {"type": "Expense", "name": "Rent", "amount": 1000.0, "date": future(15)},
        )
        _, run = calc_transactions(5000.0, total)
        run_sorted = run.copy()
        run_sorted["_d"] = run_sorted["date"].apply(
            lambda d: d.date() if hasattr(d, "date") else d
        )
        run_sorted = run_sorted.sort_values("_d").reset_index(drop=True)

        assert float(run_sorted["amount"].iloc[0]) == pytest.approx(5000.0)
        assert float(run_sorted["amount"].iloc[1]) == pytest.approx(8000.0)
        assert float(run_sorted["amount"].iloc[-1]) == pytest.approx(7000.0)

    def test_same_day_transactions_grouped(self):
        """Multiple transactions on the same date are applied as a net amount."""
        total = make_total(
            {"type": "Income", "name": "SalaryA", "amount": 2000.0, "date": future(10)},
            {"type": "Income", "name": "SalaryB", "amount": 1000.0, "date": future(10)},
            {"type": "Expense", "name": "Rent", "amount": 500.0, "date": future(10)},
        )
        _, run = calc_transactions(1000.0, total)
        # Net on day 10: +2000 +1000 -500 = +2500 → balance 3500
        assert float(run["amount"].iloc[-1]) == pytest.approx(3500.0)

    def test_multiple_expenses_accumulate_correctly(self):
        total = make_total(
            {"type": "Expense", "name": "Rent", "amount": 1000.0, "date": future(10)},
            {"type": "Expense", "name": "Utilities", "amount": 200.0, "date": future(20)},
            {"type": "Expense", "name": "Subscriptions", "amount": 50.0, "date": future(30)},
        )
        _, run = calc_transactions(10000.0, total)
        assert float(run["amount"].iloc[-1]) == pytest.approx(8750.0)

    def test_run_starts_at_current_balance(self):
        total = make_total(
            {"type": "Expense", "name": "Rent", "amount": 100.0, "date": future(5)}
        )
        _, run = calc_transactions(12345.67, total)
        assert float(run["amount"].iloc[0]) == pytest.approx(12345.67)


# ── Tests: 90-day window boundary ────────────────────────────────────────────


class TestNinetyDayWindow:
    def test_transaction_exactly_on_day_90_excluded_from_trans(self):
        """The window is strictly open: date must be > today AND < today+90."""
        total = make_total(
            {"type": "Income", "name": "Pay", "amount": 1000.0, "date": future(90)}
        )
        trans, _ = calc_transactions(5000.0, total)
        assert trans.empty

    def test_transaction_on_day_89_included_in_trans(self):
        total = make_total(
            {"type": "Income", "name": "Pay", "amount": 1000.0, "date": future(89)}
        )
        trans, _ = calc_transactions(5000.0, total)
        assert not trans.empty

    def test_transaction_today_excluded_from_trans(self):
        """Transactions on today are NOT included in the upcoming transactions list."""
        total = make_total(
            {"type": "Income", "name": "TodayPay", "amount": 1000.0, "date": date.today()}
        )
        trans, _ = calc_transactions(5000.0, total)
        assert trans.empty


# ── Tests: SKIP marker ───────────────────────────────────────────────────────


class TestSkipMarker:
    def test_skip_named_transaction_excluded_from_trans(self):
        """Transactions whose name contains '(SKIP)' must not appear in trans."""
        total = make_total(
            {"type": "Income", "name": "Salary (SKIP)", "amount": 3000.0, "date": future(15)},
            {"type": "Expense", "name": "Rent", "amount": 1000.0, "date": future(10)},
        )
        trans, _ = calc_transactions(5000.0, total)
        names = list(trans["name"])
        assert not any("(SKIP)" in n for n in names)
        assert "Rent" in names

    def test_skip_still_affects_run_balance(self):
        """Even a skipped transaction's amount is applied to the running balance."""
        total = make_total(
            {"type": "Income", "name": "Salary (SKIP)", "amount": 3000.0, "date": future(15)}
        )
        _, run = calc_transactions(5000.0, total)
        assert float(run["amount"].iloc[-1]) == pytest.approx(8000.0)


# ── Tests: calc_schedule frequency expansion ─────────────────────────────────
# These tests use SimpleNamespace mock schedule objects and require a Flask app
# context (via the app_ctx fixture) because calc_schedule calls db.session.commit().
# All schedules use future start dates so no ORM mutations or deletes are triggered.


class TestCalcScheduleFrequencies:
    def test_monthly_schedule_produces_13_entries(self, app_ctx):
        """Monthly expansion generates exactly 13 entries (months=13 constant)."""
        s = make_schedule_obj("Rent", 1000, "Monthly", days_offset=5, type_="Expense")
        total, _ = calc_schedule([s], [], [], [])
        rows = total[total["name"] == "Rent"]
        assert len(rows) == 13

    def test_biweekly_schedule_produces_27_entries(self, app_ctx):
        """BiWeekly expansion generates exactly 27 entries (biweeks=27 constant)."""
        s = make_schedule_obj("BiWeeklyPay", 500, "BiWeekly", days_offset=14, type_="Income")
        total, _ = calc_schedule([s], [], [], [])
        rows = total[total["name"] == "BiWeeklyPay"]
        assert len(rows) == 27

    def test_quarterly_schedule_produces_4_entries(self, app_ctx):
        s = make_schedule_obj("QuarterlyBonus", 5000, "Quarterly", days_offset=10, type_="Income")
        total, _ = calc_schedule([s], [], [], [])
        rows = total[total["name"] == "QuarterlyBonus"]
        assert len(rows) == 4

    def test_yearly_schedule_produces_1_entry(self, app_ctx):
        s = make_schedule_obj("AnnualFee", 200, "Yearly", days_offset=10, type_="Expense")
        total, _ = calc_schedule([s], [], [], [])
        rows = total[total["name"] == "AnnualFee"]
        assert len(rows) == 1

    def test_onetime_future_produces_1_entry(self, app_ctx):
        s = make_schedule_obj("OneTimePurchase", 500, "Onetime", days_offset=10, type_="Expense")
        total, _ = calc_schedule([s], [], [], [])
        rows = total[total["name"] == "OneTimePurchase"]
        assert len(rows) == 1

    def test_income_schedule_rolled_back_to_business_day(self, app_ctx):
        """Monthly income dates should be rolled back to the nearest preceding business day."""
        s = make_schedule_obj("Salary", 3000, "Monthly", days_offset=5, type_="Income")
        total, _ = calc_schedule([s], [], [], [])
        rows = total[total["name"] == "Salary"]
        for d in rows["date"]:
            assert d.weekday() < 5, f"Income date {d} is a weekend day"

    def test_empty_schedule_list_returns_empty_dataframe(self, app_ctx):
        total, total_scenario = calc_schedule([], [], [], [])
        assert total.empty
        assert total_scenario.empty

    def test_schedule_entries_appear_in_both_dicts(self, app_ctx):
        """Schedule entries must appear in both total and total_scenario."""
        s = make_schedule_obj("Salary", 3000, "Monthly", days_offset=5, type_="Income")
        total, total_scenario = calc_schedule([s], [], [], [])
        assert len(total) == len(total_scenario)
        assert len(total[total["name"] == "Salary"]) == 13


# ── Tests: 90-day projection end-to-end ─────────────────────────────────────


class TestEndToEndProjection:
    def test_simple_90_day_projection_ending_balance(self, app_ctx):
        """
        A single monthly $1 000 expense with $5 000 starting balance:
        All 13 monthly expansions are applied in the run balance.
        """
        s = make_schedule_obj("MonthlyExpense", 1000, "Monthly", days_offset=5, type_="Expense")
        total, _ = calc_schedule([s], [], [], [])
        _, run = calc_transactions(5000.0, total)

        end_balance = float(run["amount"].iloc[-1])
        assert end_balance == pytest.approx(5000.0 - 13 * 1000.0)

    def test_simple_90_day_projection_lowest_balance_within_window(self, app_ctx):
        """
        With a monthly $1000 expense, lowest balance inside 90 days
        should be after 3 occurrences: 5000 - 3*1000 = 2000.
        """
        s = make_schedule_obj("MonthlyExpense", 1000, "Monthly", days_offset=5, type_="Expense")
        total, _ = calc_schedule([s], [], [], [])
        _, run = calc_transactions(5000.0, total)

        today_ = date.today()
        horizon = today_ + timedelta(days=90)
        run_copy = run.copy()
        run_copy["_d"] = run_copy["date"].apply(lambda d: d.date() if hasattr(d, "date") else d)
        run_90 = run_copy[run_copy["_d"] <= horizon]
        lowest = float(run_90["amount"].min())

        assert lowest == pytest.approx(2000.0)
