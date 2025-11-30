from django import template
from datetime import datetime

register = template.Library()

@register.filter
def date_ymd(value):
    """Format a date string or datetime to YYYY-MM-DD."""
    if not value:
        return ''
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d')
    try:
        return str(value)[:10]
    except Exception:
        return str(value) 