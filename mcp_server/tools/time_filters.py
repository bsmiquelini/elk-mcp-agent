"""
Utilitários compartilhados para interpretar janelas temporais nas tools MCP.

Formatos suportados em `time_range`:
- relativo: `7d`, `24h`, `12w`, `3m`, `1y`
- dia absoluto: `2026-04-23`
- intervalo absoluto: `2026-04-01..2026-04-23`
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import re
from zoneinfo import ZoneInfo


_RELATIVE_PATTERN = re.compile(r"^\d+[hdwmy]$")
_ABSOLUTE_DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ABSOLUTE_RANGE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})$")
_APP_TIMEZONE = ZoneInfo("America/Sao_Paulo")


def build_time_range_clause(time_field: str, time_range: str | None) -> dict:
    return {"range": {time_field: _parse_time_range_bounds(time_range)}}


def _parse_time_range_bounds(time_range: str | None) -> dict:
    normalized = str(time_range or "7d").strip()

    if _RELATIVE_PATTERN.fullmatch(normalized):
        return {"gte": f"now-{normalized}", "lte": "now"}

    range_match = _ABSOLUTE_RANGE_PATTERN.fullmatch(normalized)
    if range_match:
        start_day = date.fromisoformat(range_match.group(1))
        end_day = date.fromisoformat(range_match.group(2))
        if end_day < start_day:
            start_day, end_day = end_day, start_day
        start_dt, _ = _day_bounds(start_day)
        _, end_dt = _day_bounds(end_day)
        return {"gte": start_dt.isoformat(), "lte": end_dt.isoformat()}

    if _ABSOLUTE_DAY_PATTERN.fullmatch(normalized):
        start_dt, end_dt = _day_bounds(date.fromisoformat(normalized))
        return {"gte": start_dt.isoformat(), "lte": end_dt.isoformat()}

    raise ValueError(
        "Formato de time_range não suportado. Use relativo (ex: 7d), "
        "dia absoluto (YYYY-MM-DD) ou intervalo absoluto (YYYY-MM-DD..YYYY-MM-DD)."
    )


def _day_bounds(value: date) -> tuple[datetime, datetime]:
    start = datetime(value.year, value.month, value.day, tzinfo=_APP_TIMEZONE)
    end = start + timedelta(days=1) - timedelta(microseconds=1)
    return start, end
