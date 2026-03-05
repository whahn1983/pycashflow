"""
AI cash flow insights using the OpenAI API.
Builds a 90-day projection payload from the user's schedule and queries
gpt-4o-mini for risk, pattern, and observation insights.
"""
import json
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from openai import OpenAI

from .cashflow import update_cash
from .crypto_utils import decrypt_password


SYSTEM_PROMPT = (
    "You are a financial projection assistant analyzing a projected cash balance and a schedule of future transactions.\n\n"
    "The data represents projected cash flow, not actual bank transactions.\n\n"
    "Input data format:\n"
    "You will receive a JSON object with the following fields:\n"
    "- today (string, YYYY-MM-DD): the current date to use as the reference point for all relative timing language.\n"
    "- analysis_horizon_days (integer): how many days forward the projection covers.\n"
    "- current_balance (number): the starting projected cash balance.\n"
    "- lowest_projected_balance (object): { amount (number), date (string YYYY-MM-DD) } — the lowest balance point within the horizon.\n"
    "- schedule_table (array of objects): each entry has name (string), amount (number, negative = expense), frequency (string), next_date "
    "(string YYYY-MM-DD), and type ('income' or 'expense').\n"
    "- projected_daily_balances (array of objects): each entry has date (string YYYY-MM-DD) and balance (number), representing the "
    "authoritative pre-calculated daily balance for each date in the horizon.\n"
    "- minimum_safe_balance (number): pre-calculated server-side threshold tied to near-term expense pressure.\n"
    "- low_balance_observation_warranted (boolean): pre-calculated server-side flag. True only when a low-balance observation should be "
    "allowed. Do not re-evaluate or override this flag.\n\n"
    "Your task is to identify potential cash flow risks, patterns in the schedule, and helpful financial insights.\n\n"
    "Hard rules (must follow):\n"
    "1) Data boundaries\n"
    "- Only use the data provided.\n"
    "- Do not assume additional income, expenses, account details, or user behavior.\n"
    "- If the data does not support an insight, return fewer insights rather than guessing (including zero).\n\n"
    "2) Authoritative balances\n"
    "- Use projected_daily_balances as ground truth for all balance values and dates.\n"
    "- Never recalculate balances from schedule_table.\n"
    "- Never cite a balance figure that does not appear in projected_daily_balances.\n"
    "- Transaction amounts from schedule_table may be referenced by name and amount.\n"
    "- Do not compute or report derived balance figures such as differences, margins, or gaps between two balances.\n\n"
    "3) Risk definition\n"
    "- A risk exists only if projected balance goes below zero on at least one date.\n"
    "- If projected balance remains zero or positive for the entire horizon, do not output a risk insight.\n"
    "- A drop that stays positive is not a risk.\n\n"
    "4) Low-balance observation gate\n"
    "- Only generate a low-balance observation when low_balance_observation_warranted is true.\n"
    "- Do not recompute or override this gate.\n\n"
    "5) Pattern significance\n"
    "- Do not report a pattern unless the combined value of involved transactions exceeds 10% of current_balance.\n"
    "- When citing specific transactions in a pattern, only cite transactions that each independently exceed 10% of current_balance.\n"
    "- A cluster pattern exists only when all involved transactions fall within the same 14-day window.\n"
    "- Do not group transactions separated by more than 14 days into the same cluster.\n\n"
    "6) Timing and date language\n"
    "- Use the today field for all relative timing language.\n"
    "- Verify chronological order before describing timing relationships.\n"
    "- Use 'shortly after', 'soon after', or 'right after' only when events are within 7 days of each other.\n"
    "- For events 8+ days apart, use neutral phrasing (for example: 'later in the month').\n"
    "- Format all dates as friendly text (for example: 'March 12th'). Omit the year unless the projection spans multiple calendar years.\n\n"
    "7) Insight usefulness\n"
    "- Focus on timing conflicts, recurring expense pressure, and large transaction effects.\n"
    "- Keep explanations concise and practical.\n"
    "- Do not provide tax, legal, or investment advice.\n"
    "- Insights may all be the same type. Do not force variety across risk, pattern, and observation.\n"
    "- It is acceptable to return an empty insights array.\n\n"
    "Insight type definitions:\n"
    "- risk: a specific future event/date where projected balance is below zero.\n"
    "- pattern: recurring behavior across multiple transactions that passes the significance rules above.\n"
    "- observation: a noteworthy non-recurring fact that is neither a risk nor a recurring pattern.\n\n"
    "Return results as JSON with this structure:\n\n"
    "{\n"
    '  "insights": [\n'
    "    {\n"
    '      "type": "risk | pattern | observation",\n'
    '      "severity": "low | medium | high",\n'
    '      "title": "Short descriptive title",\n'
    '      "description": "1-2 sentence explanation referencing the projection data"\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "Severity is required for every insight and is independent of insight type.\n"
    "- high: specific near-term issue with concrete action possible right now.\n"
    "- medium: meaningful pressure or structural stress that is real but less single-step actionable.\n"
    "- low: noteworthy but limited urgency/actionability.\n"
    "Do not let severity decide whether an insight exists; determine validity using the rules above first.\n\n"
    "Return up to 4 insights maximum. 0 insights is valid when no meaningful findings are supported by the data."
)



def calculate_minimum_safe_balance(run_90, min_amount, lowest_balance_date):
    """
    Calculate the balance drop over the 14 days leading up to the lowest
    balance point, using the authoritative run data (which reflects all
    recurring expansions, business-day adjustments, holds, and skips).

    Returns max(0, balance_at_window_start - min_amount), i.e. the net
    drawdown pressure in the window.  When income in the window offsets
    expenses the drop is small and the threshold stays low, suppressing
    false low-balance observations.
    """
    window_start = lowest_balance_date - timedelta(days=14)
    before_window = run_90[run_90['date_val'] <= window_start]
    if before_window.empty:
        # No data before the window — use the first available balance
        balance_at_window_start = float(run_90.iloc[0]['amount'])
    else:
        balance_at_window_start = float(before_window.iloc[-1]['amount'])
    return max(0.0, balance_at_window_start - min_amount)


def build_payload(current_balance, schedules, holds, skips):
    """Build the JSON payload sent to OpenAI from the user's cash flow data."""
    _, run, _ = update_cash(current_balance, schedules, holds, skips, [])

    todaydate = datetime.today().date()
    horizon = todaydate + relativedelta(days=90)

    min_amount = current_balance
    min_date = str(todaydate)
    min_date_val = todaydate
    run_90 = None
    projected_daily_balances = []
    if not run.empty:
        run_copy = run.copy()
        run_copy['date_val'] = run_copy['date'].apply(
            lambda d: d if hasattr(d, 'year') else datetime.strptime(str(d), '%Y-%m-%d').date()
        )
        run_90 = run_copy[run_copy['date_val'] <= horizon]
        if not run_90.empty:
            run_90 = run_90.copy()
            run_90['amount'] = run_90['amount'].astype(float)
            min_idx = run_90['amount'].idxmin()
            min_amount = float(run_90.loc[min_idx, 'amount'])
            min_date_val = run_90.loc[min_idx, 'date_val']
            min_date = str(min_date_val)
            projected_daily_balances = sorted(
                [
                    {'date': str(row['date_val']), 'balance': float(row['amount'])}
                    for _, row in run_90.iterrows()
                ],
                key=lambda x: x['date'],
            )

    lowest_balance_date = (
        min_date_val
        if hasattr(min_date_val, 'year')
        else datetime.strptime(min_date, '%Y-%m-%d').date()
    )
    minimum_safe_balance = (
        calculate_minimum_safe_balance(run_90, min_amount, lowest_balance_date)
        if run_90 is not None
        else 0.0
    )

    schedule_table = [
        {
            'name': s.name,
            'amount': float(s.amount),
            'frequency': s.frequency.lower() if s.frequency else 'onetime',
            'next_date': str(s.startdate) if s.startdate else str(todaydate),
            'type': 'income' if s.type == 'Income' else 'expense',
        }
        for s in schedules
    ]

    low_balance_observation_warranted = min_amount < minimum_safe_balance

    return {
        'today': str(todaydate),
        'analysis_horizon_days': 90,
        'current_balance': current_balance,
        'lowest_projected_balance': {'amount': min_amount, 'date': min_date},
        'minimum_safe_balance': minimum_safe_balance,
        'low_balance_observation_warranted': low_balance_observation_warranted,
        'schedule_table': schedule_table,
        'projected_daily_balances': projected_daily_balances,
    }


DEFAULT_MODEL = 'gpt-4o-mini'


def validate_model(api_key, model_name):
    """
    Check whether model_name is a valid model accessible with the given API key.
    Returns (True, None) if valid, (False, error_message) otherwise.
    """
    from openai import NotFoundError, AuthenticationError
    client = OpenAI(api_key=api_key)
    try:
        client.models.retrieve(model_name)
        return True, None
    except NotFoundError:
        return False, f"Model '{model_name}' does not exist or is not accessible with this API key."
    except AuthenticationError:
        return False, "Invalid API key — could not validate the model."
    except Exception as e:
        return False, f"Could not validate model: {e}"


def fetch_insights(encrypted_api_key, current_balance, schedules, holds, skips, model=None):
    """
    Decrypt the API key, build the payload, call OpenAI, and return the raw
    JSON string of insights.

    Raises ValueError for configuration errors, Exception for API errors.
    """
    api_key = decrypt_password(encrypted_api_key)
    payload = build_payload(current_balance, schedules, holds, skips)
    selected_model = model if model else DEFAULT_MODEL

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=selected_model,
        messages=[
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': json.dumps(payload)},
        ],
        response_format={'type': 'json_object'},
    )
    return response.choices[0].message.content
