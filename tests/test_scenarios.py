"""
Tests for the scenario engine.

Scenarios are "what-if" overlays applied on top of the base schedule.
The projection functions expose this via the total_scenario DataFrame and the
run_scenario return value from update_cash().

These tests focus on the observable CONTRACT:
  - Adding income via a scenario increases the projected ending balance.
  - Adding an expense via a scenario decreases it.
  - The baseline (schedule-only) projection is not mutated when scenarios run.
  - update_cash returns run_scenario=None when no scenarios are provided.
  - update_cash returns a non-None run_scenario when scenarios are provided.

Tests at the calc_transactions level (pure function) need no fixture.
Tests that call update_cash() or calc_schedule() need the ``app_ctx`` fixture
because calc_schedule() calls db.session.commit() for bookkeeping.
"""

import types
from datetime import date, timedelta

import pandas as pd
import pytest

from app.cashflow import calc_transactions, calc_schedule, update_cash


# ── Helpers ───────────────────────────────────────────────────────────────────

def future(days: int) -> date:
    return date.today() + timedelta(days=days)


def make_total(*rows) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def make_schedule_obj(name, amount, frequency, days_offset=30, type_="Income"):
    """
    SimpleNamespace mimicking a Schedule ORM object with a future start date.
    Future dates ensure calc_schedule()'s date-advance / delete paths are skipped.
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


def end_balance(run: pd.DataFrame) -> float:
    return float(run["amount"].iloc[-1])


# ── Tests: update_cash scenario flag ─────────────────────────────────────────


class TestUpdateCashScenarioFlag:
    """update_cash should set run_scenario=None when no scenarios given."""

    def test_no_scenarios_returns_run_scenario_none(self, app_ctx):
        trans, run, run_scenario = update_cash(5000.0, [], [], [], [])
        assert run_scenario is None

    def test_with_scenarios_returns_non_none_run_scenario(self, app_ctx):
        s = make_schedule_obj("Salary", 3000, "Monthly", days_offset=5, type_="Income")
        sc = make_schedule_obj("NewContract", 2000, "Monthly", days_offset=5, type_="Income")
        _, _, run_scenario = update_cash(5000.0, [s], [], [], [sc])
        assert run_scenario is not None

    def test_run_scenario_is_dataframe(self, app_ctx):
        s = make_schedule_obj("Salary", 3000, "Monthly", days_offset=5, type_="Income")
        sc = make_schedule_obj("NewContract", 1000, "Monthly", days_offset=5, type_="Income")
        _, _, run_scenario = update_cash(5000.0, [s], [], [], [sc])
        assert isinstance(run_scenario, pd.DataFrame)

    def test_run_scenario_has_amount_and_date_columns(self, app_ctx):
        s = make_schedule_obj("Salary", 3000, "Monthly", days_offset=5, type_="Income")
        sc = make_schedule_obj("NewContract", 1000, "Monthly", days_offset=5, type_="Income")
        _, _, run_scenario = update_cash(5000.0, [s], [], [], [sc])
        assert "amount" in run_scenario.columns
        assert "date" in run_scenario.columns


# ── Tests: scenario changes the projection (pure calc_transactions) ───────────


class TestScenarioChangesProjection:
    """
    Validate that scenario content changes the projected balance as expected.

    These tests use calc_transactions directly (no DB required) with manually
    constructed DataFrames, simulating what calc_schedule() would produce for
    base vs. scenario totals.
    """

    def test_adding_income_scenario_increases_end_balance(self):
        """
        Base: one monthly $1 000 expense.
        Scenario: same expense + a new $2 000 monthly income.
        Scenario end balance must exceed base end balance.
        """
        base_total = make_total(
            {"type": "Expense", "name": "Rent", "amount": 1000.0, "date": future(10)},
        )
        scenario_total = make_total(
            {"type": "Expense", "name": "Rent", "amount": 1000.0, "date": future(10)},
            {"type": "Income", "name": "NewContract", "amount": 2000.0, "date": future(20)},
        )
        _, run_base = calc_transactions(5000.0, base_total)
        _, run_sc = calc_transactions(5000.0, scenario_total)

        assert end_balance(run_sc) > end_balance(run_base)

    def test_adding_expense_scenario_decreases_end_balance(self):
        """
        Base: one monthly $2 000 income.
        Scenario: same income + a new $800 monthly expense.
        Scenario end balance must be lower than base end balance.
        """
        base_total = make_total(
            {"type": "Income", "name": "Salary", "amount": 2000.0, "date": future(15)},
        )
        scenario_total = make_total(
            {"type": "Income", "name": "Salary", "amount": 2000.0, "date": future(15)},
            {"type": "Expense", "name": "NewLease", "amount": 800.0, "date": future(25)},
        )
        _, run_base = calc_transactions(5000.0, base_total)
        _, run_sc = calc_transactions(5000.0, scenario_total)

        assert end_balance(run_sc) < end_balance(run_base)

    def test_scenario_income_delta_matches_expected_amount(self):
        """Scenario adds exactly one income event; delta == that income amount."""
        income_amount = 2500.0
        base_total = make_total(
            {"type": "Expense", "name": "Rent", "amount": 1000.0, "date": future(10)},
        )
        scenario_total = make_total(
            {"type": "Expense", "name": "Rent", "amount": 1000.0, "date": future(10)},
            {"type": "Income", "name": "Bonus", "amount": income_amount, "date": future(20)},
        )
        _, run_base = calc_transactions(5000.0, base_total)
        _, run_sc = calc_transactions(5000.0, scenario_total)

        delta = end_balance(run_sc) - end_balance(run_base)
        assert delta == pytest.approx(income_amount)

    def test_scenario_expense_delta_matches_expected_amount(self):
        expense_amount = 1200.0
        base_total = make_total(
            {"type": "Income", "name": "Salary", "amount": 3000.0, "date": future(15)},
        )
        scenario_total = make_total(
            {"type": "Income", "name": "Salary", "amount": 3000.0, "date": future(15)},
            {"type": "Expense", "name": "NewCost", "amount": expense_amount, "date": future(25)},
        )
        _, run_base = calc_transactions(5000.0, base_total)
        _, run_sc = calc_transactions(5000.0, scenario_total)

        delta = end_balance(run_base) - end_balance(run_sc)
        assert delta == pytest.approx(expense_amount)

    def test_changing_income_timing_affects_dip_depth(self):
        """
        Same income amount, but arriving BEFORE vs. AFTER a large expense.
        The run balance should dip lower when income arrives late.
        """
        # Income arrives before expense: no deep dip
        early_income = make_total(
            {"type": "Income", "name": "Salary", "amount": 3000.0, "date": future(5)},
            {"type": "Expense", "name": "BigBill", "amount": 2000.0, "date": future(20)},
        )
        # Income arrives after expense: temporary dip
        late_income = make_total(
            {"type": "Expense", "name": "BigBill", "amount": 2000.0, "date": future(5)},
            {"type": "Income", "name": "Salary", "amount": 3000.0, "date": future(20)},
        )
        _, run_early = calc_transactions(1000.0, early_income)
        _, run_late = calc_transactions(1000.0, late_income)

        min_early = float(run_early["amount"].min())
        min_late = float(run_late["amount"].min())

        assert min_late < min_early


# ── Tests: baseline not mutated ──────────────────────────────────────────────


class TestBaselineNotMutated:
    """The baseline DataFrame must not be modified when scenario totals are built."""

    def test_base_total_unchanged_after_scenario_calc(self):
        base_total = make_total(
            {"type": "Expense", "name": "Rent", "amount": 1000.0, "date": future(10)},
            {"type": "Income", "name": "Salary", "amount": 3000.0, "date": future(20)},
        )
        original_values = base_total.copy(deep=True)

        scenario_total = make_total(
            {"type": "Expense", "name": "Rent", "amount": 1000.0, "date": future(10)},
            {"type": "Income", "name": "Salary", "amount": 3000.0, "date": future(20)},
            {"type": "Income", "name": "Bonus", "amount": 5000.0, "date": future(30)},
        )

        calc_transactions(5000.0, base_total)
        calc_transactions(5000.0, scenario_total)

        pd.testing.assert_frame_equal(base_total, original_values)

    def test_scenario_calc_does_not_alter_run_values(self):
        """The base run and the scenario run are independent DataFrames."""
        base_total = make_total(
            {"type": "Income", "name": "Salary", "amount": 2000.0, "date": future(15)},
        )
        scenario_total = make_total(
            {"type": "Income", "name": "Salary", "amount": 2000.0, "date": future(15)},
            {"type": "Expense", "name": "Extra", "amount": 500.0, "date": future(25)},
        )
        _, run_base = calc_transactions(5000.0, base_total)
        _, run_sc = calc_transactions(5000.0, scenario_total)

        assert end_balance(run_base) != end_balance(run_sc)
        # Re-run base to verify it hasn't been mutated
        _, run_base_again = calc_transactions(5000.0, base_total)
        assert end_balance(run_base) == pytest.approx(end_balance(run_base_again))


# ── Tests: scenario comparison min/end balance differences ──────────────────


class TestScenarioComparison:
    """
    If the caller compares scenario vs. baseline projections, the differences in
    minimum and ending balance should track the added/removed cash events.
    """

    def test_scenario_with_large_income_has_higher_min_balance(self):
        """Adding a large income injection raises the minimum balance over the horizon."""
        base_total = make_total(
            {"type": "Expense", "name": "Rent", "amount": 3000.0, "date": future(5)},
            {"type": "Expense", "name": "Bills", "amount": 1000.0, "date": future(45)},
        )
        scenario_total = make_total(
            {"type": "Expense", "name": "Rent", "amount": 3000.0, "date": future(5)},
            {"type": "Expense", "name": "Bills", "amount": 1000.0, "date": future(45)},
            {"type": "Income", "name": "NewClient", "amount": 5000.0, "date": future(3)},
        )
        _, run_base = calc_transactions(4000.0, base_total)
        _, run_sc = calc_transactions(4000.0, scenario_total)

        min_base = float(run_base["amount"].min())
        min_sc = float(run_sc["amount"].min())

        assert min_sc > min_base

    def test_no_scenario_end_balance_equals_base_end_balance(self, app_ctx):
        """
        When scenarios are empty, run_scenario is None and run reflects
        only the base schedule.
        """
        s = make_schedule_obj("MonthlyRent", 1000, "Monthly", days_offset=5, type_="Expense")
        _, run, run_scenario = update_cash(5000.0, [s], [], [], [])

        assert run_scenario is None
        assert end_balance(run) < 5000.0  # expenses reduced the balance
