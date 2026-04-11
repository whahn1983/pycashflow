"""Lightweight serialization helpers for PyCashFlow API v1.

Each ``serialize_*`` function accepts an ORM model instance and returns a
plain ``dict`` suitable for JSON encoding.  No external dependencies are
required — conversion rules follow the conventions in ``API_CONVENTIONS.md``:

- Dates       → ISO 8601 string ``"YYYY-MM-DD"``
- Datetimes   → ISO 8601 UTC string ``"YYYY-MM-DDTHH:MM:SSZ"``
- Amounts     → string with 2 decimal places ``"1234.56"``
  (avoids floating-point representation errors for currency)
"""

from decimal import Decimal
from datetime import date, datetime, timezone


# ── Primitive converters ──────────────────────────────────────────────────────

def _date(value) -> str | None:
    """Convert a ``datetime.date`` to ISO 8601 string, or ``None``."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def _datetime(value) -> str | None:
    """Convert a ``datetime.datetime`` to UTC ISO 8601 string, or ``None``."""
    if value is None:
        return None
    if value.tzinfo is None:
        # Treat naive datetimes as UTC (all DB datetimes in this app are UTC).
        value = value.replace(tzinfo=timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _amount(value) -> str | None:
    """Format a ``Decimal`` (or numeric) as a 2-decimal-place string, or ``None``."""
    if value is None:
        return None
    return f"{Decimal(str(value)):.2f}"


# ── Model serializers ─────────────────────────────────────────────────────────

def serialize_user(user) -> dict:
    """Public-safe representation of a User.  Never includes password or secrets."""
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "is_admin": bool(user.admin),
        "is_global_admin": bool(user.is_global_admin),
        "twofa_enabled": bool(user.twofa_enabled),
        "is_guest": (user.owner_user_id is not None) or (user.account_owner_id is not None),
        "subscription_status": user.subscription_status,
        "subscription_source": user.subscription_source,
        "subscription_expiry": _datetime(user.subscription_expiry),
    }


def serialize_schedule(schedule) -> dict:
    return {
        "id": schedule.id,
        "name": schedule.name,
        "amount": _amount(schedule.amount),
        "type": schedule.type,
        "frequency": schedule.frequency,
        "start_date": _date(schedule.startdate),
        "first_date": _date(schedule.firstdate),
    }


def serialize_scenario(scenario) -> dict:
    return {
        "id": scenario.id,
        "name": scenario.name,
        "amount": _amount(scenario.amount),
        "type": scenario.type,
        "frequency": scenario.frequency,
        "start_date": _date(scenario.startdate),
        "first_date": _date(scenario.firstdate),
    }


def serialize_balance(balance) -> dict:
    return {
        "id": balance.id,
        "amount": _amount(balance.amount),
        "date": _date(balance.date),
    }


def serialize_hold(hold) -> dict:
    return {
        "id": hold.id,
        "name": hold.name,
        "amount": _amount(hold.amount),
        "type": hold.type,
    }


def serialize_skip(skip) -> dict:
    return {
        "id": skip.id,
        "name": skip.name,
        "date": _date(skip.date),
        "amount": _amount(skip.amount),
        "type": skip.type,
    }
