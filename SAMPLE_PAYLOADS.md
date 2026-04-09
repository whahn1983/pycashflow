# PyCashFlow Mobile API — Sample Payloads

All examples use `curl`. Replace `<token>` with a real bearer token obtained from the login endpoint.

---

## Authentication

### POST /api/v1/auth/login

**Request:**
```bash
curl -X POST https://your-server/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "s3cr3t"}'
```

**Response 200 (success):**
```json
{
  "data": {
    "token": "dG9rZW4tZXhhbXBsZS1iYXNlNjQtZW5jb2RlZA",
    "user": {
      "id": 1,
      "email": "user@example.com",
      "name": "Jane Doe",
      "is_admin": true,
      "is_global_admin": false,
      "twofa_enabled": false,
      "is_guest": false
    }
  }
}
```

**Response 401 (bad credentials):**
```json
{
  "error": "Invalid credentials or account is not active",
  "code": "unauthorized",
  "status": 401
}
```

**Response 422 (missing fields):**
```json
{
  "error": "Validation failed",
  "code": "validation_error",
  "status": 422,
  "fields": {
    "email": "Email is required",
    "password": "Password is required"
  }
}
```

---

### POST /api/v1/auth/logout

**Request:**
```bash
curl -X POST https://your-server/api/v1/auth/logout \
  -H "Authorization: Bearer <token>"
```

**Response 200:**
```json
{
  "data": {
    "message": "Logged out"
  }
}
```

---

### GET /api/v1/auth/me

**Request:**
```bash
curl https://your-server/api/v1/auth/me \
  -H "Authorization: Bearer <token>"
```

**Response 200:**
```json
{
  "data": {
    "id": 1,
    "email": "user@example.com",
    "name": "Jane Doe",
    "is_admin": true,
    "is_global_admin": false,
    "twofa_enabled": false,
    "is_guest": false
  }
}
```

---

## Data Endpoints

### GET /api/v1/dashboard

Returns a mobile-friendly dashboard summary with current balance, cash risk score, upcoming transactions, and minimum projected balance.

**Request:**
```bash
curl https://your-server/api/v1/dashboard \
  -H "Authorization: Bearer <token>"
```

**Response 200:**
```json
{
  "data": {
    "balance": "5000.00",
    "balance_date": "2026-04-09",
    "risk": {
      "score": 82,
      "status": "Safe",
      "color": "green",
      "runway_days": 45.3,
      "lowest_balance": 2150.50,
      "days_to_lowest": 28,
      "avg_daily_expense": 110.75,
      "days_below_threshold": 0,
      "pct_below_threshold": 0.0,
      "recovery_days": 0,
      "near_term_buffer": 4200.00
    },
    "upcoming_transactions": [
      {
        "name": "Payroll",
        "type": "Income",
        "amount": "3500.00",
        "date": "2026-04-15"
      },
      {
        "name": "Rent",
        "type": "Expense",
        "amount": "1800.00",
        "date": "2026-05-01"
      },
      {
        "name": "Internet",
        "type": "Expense",
        "amount": "89.99",
        "date": "2026-05-03"
      }
    ],
    "min_balance": "2150.50"
  }
}
```

**Response 200 (no schedules / fresh account):**
```json
{
  "data": {
    "balance": "5000.00",
    "balance_date": "2026-04-09",
    "risk": {
      "score": 50,
      "status": "Watch",
      "color": "yellow",
      "runway_days": 0,
      "lowest_balance": 5000.0,
      "days_to_lowest": 0,
      "avg_daily_expense": 0,
      "days_below_threshold": 0,
      "pct_below_threshold": 0.0,
      "recovery_days": null,
      "near_term_buffer": 5000.0
    },
    "upcoming_transactions": [],
    "min_balance": "5000.00"
  }
}
```

---

### GET /api/v1/schedules

Returns all recurring scheduled transactions for the authenticated user (or account owner for guests).

**Request:**
```bash
curl https://your-server/api/v1/schedules \
  -H "Authorization: Bearer <token>"
```

**Response 200:**
```json
{
  "data": [
    {
      "id": 1,
      "name": "Payroll",
      "amount": "3500.00",
      "type": "Income",
      "frequency": "BiWeekly",
      "start_date": "2026-04-18",
      "first_date": "2026-01-10"
    },
    {
      "id": 2,
      "name": "Rent",
      "amount": "1800.00",
      "type": "Expense",
      "frequency": "Monthly",
      "start_date": "2026-05-01",
      "first_date": "2025-06-01"
    },
    {
      "id": 3,
      "name": "Car Insurance",
      "amount": "450.00",
      "type": "Expense",
      "frequency": "Quarterly",
      "start_date": "2026-07-01",
      "first_date": "2025-01-01"
    }
  ],
  "meta": {
    "total": 3
  }
}
```

**Response 200 (empty):**
```json
{
  "data": [],
  "meta": {
    "total": 0
  }
}
```

---

### GET /api/v1/projections

Returns running-balance data points for chart rendering. The `schedule` series is always present; the `scenario` series is included only when the user has what-if scenarios configured.

**Request:**
```bash
curl https://your-server/api/v1/projections \
  -H "Authorization: Bearer <token>"
```

**Response 200 (with scenarios):**
```json
{
  "data": {
    "schedule": [
      { "date": "2026-04-09", "amount": "5000.00" },
      { "date": "2026-04-15", "amount": "8500.00" },
      { "date": "2026-04-18", "amount": "8410.01" },
      { "date": "2026-05-01", "amount": "6610.01" },
      { "date": "2026-05-15", "amount": "10110.01" }
    ],
    "scenario": [
      { "date": "2026-04-09", "amount": "5000.00" },
      { "date": "2026-04-15", "amount": "8500.00" },
      { "date": "2026-04-20", "amount": "8000.00" },
      { "date": "2026-05-01", "amount": "6200.00" },
      { "date": "2026-05-15", "amount": "9700.00" }
    ]
  }
}
```

**Response 200 (no scenarios):**
```json
{
  "data": {
    "schedule": [
      { "date": "2026-04-09", "amount": "5000.00" }
    ],
    "scenario": null
  }
}
```

---

### GET /api/v1/scenarios

Returns what-if scenario items.

**Request:**
```bash
curl https://your-server/api/v1/scenarios \
  -H "Authorization: Bearer <token>"
```

**Response 200:**
```json
{
  "data": [
    {
      "id": 10,
      "name": "New Car Payment",
      "amount": "500.00",
      "type": "Expense",
      "frequency": "Monthly",
      "start_date": "2026-05-01",
      "first_date": "2026-05-01"
    }
  ],
  "meta": {
    "total": 1
  }
}
```

---

### GET /api/v1/holds

Returns paused (held) schedule items. A hold offsets a schedule's recurring amount.

**Request:**
```bash
curl https://your-server/api/v1/holds \
  -H "Authorization: Bearer <token>"
```

**Response 200:**
```json
{
  "data": [
    {
      "id": 5,
      "name": "Gym Membership",
      "amount": "50.00",
      "type": "Expense"
    }
  ],
  "meta": {
    "total": 1
  }
}
```

---

### GET /api/v1/skips

Returns skipped individual transaction instances (one-time exemptions from a recurring schedule).

**Request:**
```bash
curl https://your-server/api/v1/skips \
  -H "Authorization: Bearer <token>"
```

**Response 200:**
```json
{
  "data": [
    {
      "id": 7,
      "name": "Internet",
      "date": "2026-05-03",
      "amount": "89.99",
      "type": "Expense"
    }
  ],
  "meta": {
    "total": 1
  }
}
```

---

## Endpoint Summary

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/auth/login` | None | Authenticate, receive bearer token |
| POST | `/api/v1/auth/logout` | Bearer | Revoke current token |
| GET | `/api/v1/auth/me` | Bearer | Current user profile |
| GET | `/api/v1/dashboard` | Bearer | Balance, risk score, upcoming transactions |
| GET | `/api/v1/schedules` | Bearer | List recurring scheduled items |
| GET | `/api/v1/projections` | Bearer | Running-balance projection data points |
| GET | `/api/v1/scenarios` | Bearer | List what-if scenarios |
| GET | `/api/v1/holds` | Bearer | List paused schedule items |
| GET | `/api/v1/skips` | Bearer | List skipped transaction instances |

## Notes for SwiftUI Clients

- **Amounts** are always returned as strings with exactly 2 decimal places (`"1234.56"`) to avoid floating-point precision issues. Parse with `Decimal` or `NSDecimalNumber`, not `Double`.
- **Dates** use ISO 8601 format (`"YYYY-MM-DD"`). Use a `DateFormatter` with `"yyyy-MM-dd"` format.
- **Risk score** is an integer 0-100 (higher = safer). Map `color` to your UI theme colors.
- **Empty collections** return `"data": []` with `"meta": {"total": 0}`, never `null`.
- The `scenario` field in `/projections` is `null` when no scenarios exist.
