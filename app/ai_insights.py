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
    "Input data format:\n"
    "You will receive a JSON object with the following fields:\n"
    "- today (string, YYYY-MM-DD): the current date to use as the reference point for all relative timing language.\n"
    "- analysis_horizon_days (integer): how many days forward the projection covers.\n"
    "- current_balance (number): the starting projected cash balance.\n"
    "- lowest_projected_balance (object): { amount (number), date (string YYYY-MM-DD) } — the lowest balance point within the horizon.\n"
    "- schedule_table (array of objects): each entry has name (string), amount (number, negative = expense), "
    "frequency (string, e.g. 'monthly', 'weekly', 'onetime'), next_date (string YYYY-MM-DD), and type ('income' or 'expense').\n"
    "- projected_daily_balances (array of objects): each entry has date (string YYYY-MM-DD) and balance (number), representing the "
    "authoritative pre-calculated daily balance for each date in the horizon.\n\n"
    "Your task is to identify potential cash flow risks, patterns in the schedule, and helpful financial insights.\n\n"
    "Rules:\n"
    "- Only use the data provided.\n"
    "- Do not assume any additional income, expenses, or account information.\n"
    "- Focus on timing risks, recurring expense patterns, and large transactions.\n"
    "- Keep explanations concise and practical.\n"
    "- Do not provide tax, legal, or investment advice.\n"
    "- Reference specific transactions if they appear relevant and are greater than 10% of the current_balance.\n"
    "- Use the today field for all relative timing language (e.g. '3 days away', 'in 6 months').\n"
    "- If the provided data does not support a clear insight, return fewer insights rather than guessing.\n"
    "- Insights should go beyond what is visible to the user (current balance, lowest balance, a graph of projections). Focus on"
    " explaining why an insight exists, which specific transactions cause it, and any timing conflicts or clustering patterns that are"
    " not obvious from the balance curve alone.\n"
    "- A shortfall only exists when the projected balance goes negative. A balance that drops from the starting level but remains positive"
    " at all times is never a risk, regardless of how much it drops or how close it gets to zero.\n"
    "- When referencing dates, use a friendly format (e.g. March 12th) rather than ISO format. Omit the year unless the projection"
    " spans multiple calendar years.\n"
    "- Do not surface patterns unless the combined value of the transactions involved exceeds 10% of the current_balance. Small recurring"
    " items that have minimal cumulative impact on the projection are not worth reporting.\n"
    "- When describing a pattern, only name or cite individual transactions that each independently exceed 10% of the current_balance."
    " Do not list small transactions alongside large ones to make a pattern appear more significant than it is.\n"
    "- It is acceptable to return an empty insights array if the data does not support any meaningful findings.\n"
    "- Use projected_daily_balances as ground truth for all balance values. Use schedule_table only to identify which transactions"
    " explain balance movements; never recalculate balances independently from the schedule.\n"
    "- Do not perform any balance calculations from the schedule_table. All balance values must come directly from"
    " projected_daily_balances. Any balance figure not found in projected_daily_balances should not appear in any insight.\n"
    "- Do not compute or report derived balance figures such as differences, margins, or gaps between any two balance values"
    " (e.g. 'X above/below the current balance'). Only quote balance amounts that appear verbatim in projected_daily_balances.\n"
    "- lowest_projected_balance is the authoritative pre-calculated result of the projection engine including all business day rules,"
    " holds, and skips. Do not attempt to recalculate it from the schedule_table.\n\n"
    "Insight type definitions (apply consistently):\n"
    "- risk: a specific future event where the projected balance value in projected_daily_balances is below zero. An overall downward"
    " trend only qualifies as a risk if the balance reaches zero or goes negative at some point in the projection. A balance that drops"
    " below the starting balance but remains positive throughout the entire horizon is never a risk. If income before the specific event"
    " raises the balance and prevents it from going negative, it is not a risk.\n"
    "- pattern: a recurring behaviour visible across multiple transactions (e.g. several large expenses cluster at month-end).\n"
    "- observation: a one-off or general fact about the projection that is noteworthy but not a recurring pattern or an immediate risk.\n\n"
    "Insights may all be the same type if that is what the data supports. Do not force a mix of risk, pattern, and observation types.\n\n"
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
    "The severity field is required for every insight but do not allow severity to drive whether an insight exists, use only the defined rules above. "
    "Use 'high' for risks driven by a specific identifiable transaction or timing conflict that could be acted on (e.g. a large expense "
    "landing before an income deposit). Use 'medium' for patterns that create stress but are harder to act on directly (e.g. recurring expenses "
    "clustering in the same window). Use 'low' for observations that are noteworthy but unlikely to require action.\n\n"
    "Return up to 4 insights maximum but 0 is acceptable if the data does not support any meaningful findings."
)


def build_payload(current_balance, schedules, holds, skips):
    """Build the JSON payload sent to OpenAI from the user's cash flow data."""
    _, run, _ = update_cash(current_balance, schedules, holds, skips, [])

    todaydate = datetime.today().date()
    horizon = todaydate + relativedelta(days=90)

    min_amount = current_balance
    min_date = str(todaydate)
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
            min_date = str(run_90.loc[min_idx, 'date_val'])
            projected_daily_balances = sorted(
                [
                    {'date': str(row['date_val']), 'balance': float(row['amount'])}
                    for _, row in run_90.iterrows()
                ],
                key=lambda x: x['date'],
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

    return {
        'today': str(todaydate),
        'analysis_horizon_days': 90,
        'current_balance': current_balance,
        'lowest_projected_balance': {'amount': min_amount, 'date': min_date},
        'schedule_table': schedule_table,
        'projected_daily_balances': projected_daily_balances,
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
