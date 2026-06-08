import datetime
from typing import Dict

CURRENCY_SYMBOLS: Dict[str, str] = {
    "FJD": "FJ$",
    "USD": "$",
    "AUD": "A$",
    "NZD": "NZ$",
    "GBP": "£"
}

def format_currency(amount: float, currency_code: str = "FJD") -> str:
    """
    Formats a numeric amount with the proper currency symbol.
    """
    symbol = CURRENCY_SYMBOLS.get(currency_code, "$")
    try:
        return f"{symbol}{amount:,.2f}"
    except (ValueError, TypeError):
        return f"{symbol}0.00"

def format_date(d) -> str:
    """
    Formats a date object or string into DD MMM YYYY.
    """
    if not d:
        return ""
    if isinstance(d, str):
        try:
            d = datetime.date.fromisoformat(d)
        except ValueError:
            try:
                d = datetime.datetime.strptime(d, "%Y-%m-%d %H:%M:%S").date()
            except ValueError:
                return d
    return d.strftime("%d %b %Y")

def get_days_remaining(end_date) -> int:
    """
    Calculates number of days from today to end_date.
    """
    if not end_date:
        return 0
    if isinstance(end_date, str):
        end_date = datetime.date.fromisoformat(end_date)
    elif isinstance(end_date, datetime.datetime):
        end_date = end_date.date()
    
    today = datetime.date.today()
    delta = end_date - today
    return max(0, delta.days)

def calculate_percentage(part: float, total: float) -> float:
    """
    Safely calculates percentage ratio.
    """
    if not total or total <= 0:
        return 0.0
    return min(100.0, max(0.0, (part / total) * 100.0))

def get_emergency_fund_rating(months: float) -> str:
    """
    Translates month coverage to Emergency Fund health level.
    """
    if months < 1.0:
        return "Critical"
    elif months < 3.0:
        return "Poor"
    elif months < 6.0:
        return "Good"
    elif months < 9.0:
        return "Excellent"
    else:
        return "Exceptional"

def get_health_score_rating(score: float) -> str:
    """
    Translates score (0-100) to qualitative rating.
    """
    if score < 40:
        return "Critical"
    elif score < 60:
        return "Poor"
    elif score < 75:
        return "Good"
    elif score < 90:
        return "Excellent"
    else:
        return "Exceptional"
