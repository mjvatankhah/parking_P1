"""Presentation-only Persian dates; service boundaries continue to use date objects."""
from datetime import date, timedelta
from reno.ui.vendor.jalaali import Jalaali
from reno.ui import theme

WEEKDAYS = ('شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه')
MONTHS = ('فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
          'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند')


def week_bounds(day):
    start = day - timedelta(days=(day.weekday()+2) % 7)
    return start, start + timedelta(days=6)


def jalali_text(day):
    if isinstance(day, str):
        try:
            day = date.fromisoformat(day)
        except ValueError:
            return '—'
    value = Jalaali.to_jalaali(day.year, day.month, day.day)
    return theme.fa_number(f"{value['jy']:04}/{value['jm']:02}/{value['jd']:02}")


def week_text(day):
    start, end = week_bounds(day)
    return f'{jalali_text(start)} تا {jalali_text(end)}'
