"""
Shared cashflow function references for use across test modules.

conftest.py imports this module at startup — before any test-module stubs
are installed — which ensures the names below are bound to the *real*
implementations from app.cashflow even when test_cash_risk_score.py later
replaces sys.modules['app.cashflow'] with a lightweight stub.

Import from this module instead of directly from conftest so the imports
work under all pytest --import-mode settings (prepend, append, importlib).
"""

from app.cashflow import (
    calc_transactions,
    calc_schedule,
    update_cash,
)
