"""
AI cash flow insights using the OpenAI API.
Builds a 90-day projection payload from the user's schedule and queries
gpt-4o-mini for risk, pattern, and observation insights.
"""
import json
from datetime import datetime
from dateutil.relativedelta import relativedelta
from openai import OpenAI

from .cashflow import update_cash
from .crypto_utils import decrypt_password


SYSTEM_PROMPT = (
    "You are a financial projection assistant analyzing a projected cash balance and a schedule of future transactions.\n\n"
    "The data represents projected cash flow, not actual bank transactions.\n\n"
    "Your task is to identify potential cash flow risks, patterns in the schedule, and helpful financial insights.\n\n"
    "Rules:\n"
    "- Only use the data provided.\n"
    "- Do not assume any additional income, expenses, or account information.\n"
    "- Focus on timing risks, recurring expense patterns, and large transactions.\n"
    "- Keep explanations concise and practical.\n"
    "- Do not provide tax, legal, or investment advice.\n"
    "- Reference specific transactions if they appear relevant.\n"
    "- If the provided data does not support a clear insight, return fewer insights rather than guessing.\n\n"
    "Return results as JSON with this structure:\n\n"
    "{\n"
    '  "insights": [\n'
    "    {\n"
    '      "type": "risk | pattern | observation",\n'
    '      "title": "Short descriptive title",\n'
    '      "description": "1-2 sentence explanation referencing the projection data"\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "Return 2\u20134 insights maximum."
)


def build_payload(current_balance, schedules, holds, skips):
    """Build the JSON payload sent to OpenAI from the user's cash flow data."""
    _, run, _ = update_cash(current_balance, schedules, holds, skips, [])

    todaydate = datetime.today().date()
    horizon = todaydate + relativedelta(days=90)

    min_amount = current_balance
    min_date = str(todaydate)
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
            min_date = str(run_90.loc[min_idx, 'date_val'])

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

    return {
        'analysis_horizon_days': 90,
        'current_balance': current_balance,
        'lowest_projected_balance': {'amount': min_amount, 'date': min_date},
        'schedule_table': schedule_table,
    }


def fetch_insights(encrypted_api_key, current_balance, schedules, holds, skips):
    """
    Decrypt the API key, build the payload, call OpenAI, and return the raw
    JSON string of insights.

    Raises ValueError for configuration errors, Exception for API errors.
    """
    api_key = decrypt_password(encrypted_api_key)
    payload = build_payload(current_balance, schedules, holds, skips)

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': json.dumps(payload)},
        ],
        response_format={'type': 'json_object'},
    )
    return response.choices[0].message.content
