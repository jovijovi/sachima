#!/usr/bin/env python3
"""Narrow companion life tools.

These tools intentionally avoid general web/search/browser/file/terminal access.
They provide small, auditable surfaces for companion profiles: current time,
holiday lookup, weather lookup, and journal writing through the profile-scoped
memory palace.
"""

from __future__ import annotations

import json
import math
import re
import urllib.parse
import urllib.request
from datetime import date as Date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tools.registry import registry

RICH_RESULT_BEGIN = "HERMES_RICH_RESULT_JSON_BEGIN"
RICH_RESULT_END = "HERMES_RICH_RESULT_JSON_END"

_WEEKDAY_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
_WEEKDAY_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_LOCATION_ALIASES: dict[str, dict[str, Any]] = {
    "成都": {"label": "成都", "country": "中国", "lat": 30.5728, "lon": 104.0668, "timezone": "Asia/Shanghai"},
    "chengdu": {"label": "成都", "country": "中国", "lat": 30.5728, "lon": 104.0668, "timezone": "Asia/Shanghai"},
    "北京": {"label": "北京", "country": "中国", "lat": 39.9042, "lon": 116.4074, "timezone": "Asia/Shanghai"},
    "beijing": {"label": "北京", "country": "中国", "lat": 39.9042, "lon": 116.4074, "timezone": "Asia/Shanghai"},
    "上海": {"label": "上海", "country": "中国", "lat": 31.2304, "lon": 121.4737, "timezone": "Asia/Shanghai"},
    "shanghai": {"label": "上海", "country": "中国", "lat": 31.2304, "lon": 121.4737, "timezone": "Asia/Shanghai"},
    "广州": {"label": "广州", "country": "中国", "lat": 23.1291, "lon": 113.2644, "timezone": "Asia/Shanghai"},
    "深圳": {"label": "深圳", "country": "中国", "lat": 22.5431, "lon": 114.0579, "timezone": "Asia/Shanghai"},
    "杭州": {"label": "杭州", "country": "中国", "lat": 30.2741, "lon": 120.1551, "timezone": "Asia/Shanghai"},
    "london": {"label": "London", "country": "United Kingdom", "lat": 51.5072, "lon": -0.1276, "timezone": "Europe/London"},
    "new york": {"label": "New York", "country": "United States", "lat": 40.7128, "lon": -74.0060, "timezone": "America/New_York"},
    "los angeles": {"label": "Los Angeles", "country": "United States", "lat": 34.0522, "lon": -118.2437, "timezone": "America/Los_Angeles"},
    "paris": {"label": "Paris", "country": "France", "lat": 48.8566, "lon": 2.3522, "timezone": "Europe/Paris"},
    "tokyo": {"label": "Tokyo", "country": "Japan", "lat": 35.6762, "lon": 139.6503, "timezone": "Asia/Tokyo"},
}

_WMO_ZH = {
    0: "晴", 1: "晴间多云", 2: "局部多云", 3: "阴/多云",
    45: "雾", 48: "冻雾",
    51: "小毛毛雨", 53: "毛毛雨", 55: "较强毛毛雨",
    56: "冻毛毛雨", 57: "较强冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    66: "冻雨", 67: "较强冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "阵雨", 81: "较强阵雨", 82: "强阵雨",
    85: "阵雪", 86: "强阵雪",
    95: "雷暴", 96: "雷暴伴小冰雹", 99: "雷暴伴冰雹",
}

# Common lunar data table for 1900-2050. Encodes month lengths and leap month.
# Source shape is the public-domain lunarInfo table used by many almanac snippets.
_LUNAR_INFO = [
    0x04BD8, 0x04AE0, 0x0A570, 0x054D5, 0x0D260, 0x0D950, 0x16554, 0x056A0, 0x09AD0, 0x055D2,
    0x04AE0, 0x0A5B6, 0x0A4D0, 0x0D250, 0x1D255, 0x0B540, 0x0D6A0, 0x0ADA2, 0x095B0, 0x14977,
    0x04970, 0x0A4B0, 0x0B4B5, 0x06A50, 0x06D40, 0x1AB54, 0x02B60, 0x09570, 0x052F2, 0x04970,
    0x06566, 0x0D4A0, 0x0EA50, 0x06E95, 0x05AD0, 0x02B60, 0x186E3, 0x092E0, 0x1C8D7, 0x0C950,
    0x0D4A0, 0x1D8A6, 0x0B550, 0x056A0, 0x1A5B4, 0x025D0, 0x092D0, 0x0D2B2, 0x0A950, 0x0B557,
    0x06CA0, 0x0B550, 0x15355, 0x04DA0, 0x0A5D0, 0x14573, 0x052D0, 0x0A9A8, 0x0E950, 0x06AA0,
    0x0AEA6, 0x0AB50, 0x04B60, 0x0AAE4, 0x0A570, 0x05260, 0x0F263, 0x0D950, 0x05B57, 0x056A0,
    0x096D0, 0x04DD5, 0x04AD0, 0x0A4D0, 0x0D4D4, 0x0D250, 0x0D558, 0x0B540, 0x0B6A0, 0x195A6,
    0x095B0, 0x049B0, 0x0A974, 0x0A4B0, 0x0B27A, 0x06A50, 0x06D40, 0x0AF46, 0x0AB60, 0x09570,
    0x04AF5, 0x04970, 0x064B0, 0x074A3, 0x0EA50, 0x06B58, 0x055C0, 0x0AB60, 0x096D5, 0x092E0,
    0x0C960, 0x0D954, 0x0D4A0, 0x0DA50, 0x07552, 0x056A0, 0x0ABB7, 0x025D0, 0x092D0, 0x0CAB5,
    0x0A950, 0x0B4A0, 0x0BAA4, 0x0AD50, 0x055D9, 0x04BA0, 0x0A5B0, 0x15176, 0x052B0, 0x0A930,
    0x07954, 0x06AA0, 0x0AD50, 0x05B52, 0x04B60, 0x0A6E6, 0x0A4E0, 0x0D260, 0x0EA65, 0x0D530,
    0x05AA0, 0x076A3, 0x096D0, 0x04BD7, 0x04AD0, 0x0A4D0, 0x1D0B6, 0x0D250, 0x0D520, 0x0DD45,
    0x0B5A0, 0x056D0, 0x055B2, 0x049B0, 0x0A577, 0x0A4B0, 0x0AA50, 0x1B255, 0x06D20, 0x0ADA0,
]

_LUNAR_HOLIDAYS = {
    (1, 1): "春节",
    (1, 15): "元宵节",
    (5, 5): "端午节",
    (7, 7): "七夕",
    (7, 15): "中元节",
    (8, 15): "中秋节",
    (9, 9): "重阳节",
    (12, 8): "腊八节",
}

_CN_GREGORIAN = {
    (1, 1): "元旦",
    (3, 8): "国际妇女节",
    (5, 1): "劳动节",
    (6, 1): "儿童节",
    (10, 1): "国庆节",
}

_WESTERN_FIXED = {
    (1, 1): ("New Year's Day", "欧美元旦"),
    (2, 14): ("Valentine's Day", "情人节"),
    (3, 17): ("St. Patrick's Day", "圣帕特里克节"),
    (4, 1): ("April Fools' Day", "愚人节"),
    (10, 31): ("Halloween", "万圣夜"),
    (12, 24): ("Christmas Eve", "平安夜"),
    (12, 25): ("Christmas Day", "圣诞节"),
    (12, 31): ("New Year's Eve", "跨年夜"),
}


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _error(message: str, **extra: Any) -> str:
    payload = {"success": False, "error": message}
    payload.update(extra)
    return _json(payload)


def _safe_text(value: Any, *, max_len: int = 160) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def _parse_date(value: str | None = None, *, timezone: str = "Asia/Shanghai") -> Date:
    if value:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    return datetime.now(ZoneInfo(timezone)).date()


def clock_now(timezone: str = "Asia/Shanghai", task_id: str | None = None) -> str:
    """Return the current date/time for a named IANA timezone."""
    try:
        tz_name = _safe_text(timezone or "Asia/Shanghai", max_len=80) or "Asia/Shanghai"
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone: {tz_name}") from exc
        now = datetime.now(tz)
        offset = now.strftime("%z")
        offset = f"{offset[:3]}:{offset[3:]}" if len(offset) == 5 else offset
        return _json({
            "success": True,
            "timezone": tz_name,
            "iso": now.isoformat(timespec="seconds"),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "weekday_zh": _WEEKDAY_ZH[now.weekday()],
            "weekday_en": _WEEKDAY_EN[now.weekday()],
            "utc_offset": offset,
        })
    except Exception as exc:
        return _error(str(exc))


def _lunar_year_days(year: int) -> int:
    info = _LUNAR_INFO[year - 1900]
    total = 348
    bit = 0x8000
    while bit > 0x8:
        if info & bit:
            total += 1
        bit >>= 1
    return total + _leap_days(year)


def _leap_month(year: int) -> int:
    return _LUNAR_INFO[year - 1900] & 0xF


def _leap_days(year: int) -> int:
    if _leap_month(year):
        return 30 if (_LUNAR_INFO[year - 1900] & 0x10000) else 29
    return 0


def _lunar_month_days(year: int, month: int) -> int:
    return 30 if (_LUNAR_INFO[year - 1900] & (0x10000 >> month)) else 29


def _solar_to_lunar(day: Date) -> dict[str, Any]:
    if day < Date(1900, 1, 31) or day > Date(2049, 12, 31):
        return {"supported": False}
    offset = (day - Date(1900, 1, 31)).days
    year = 1900
    while year < 2050:
        days = _lunar_year_days(year)
        if offset < days:
            break
        offset -= days
        year += 1

    leap = _leap_month(year)
    is_leap = False
    month = 1
    while month <= 12:
        if leap and month == leap + 1 and not is_leap:
            month -= 1
            is_leap = True
            days = _leap_days(year)
        else:
            days = _lunar_month_days(year, month)
        if offset < days:
            break
        offset -= days
        if is_leap and month == leap:
            is_leap = False
        month += 1
    return {"supported": True, "year": year, "month": month, "day": offset + 1, "is_leap_month": is_leap}


def _nth_weekday(year: int, month: int, weekday: int, nth: int) -> Date:
    d = Date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(days=7 * (nth - 1))


def _last_weekday(year: int, month: int, weekday: int) -> Date:
    if month == 12:
        d = Date(year + 1, 1, 1) - timedelta(days=1)
    else:
        d = Date(year, month + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _easter_sunday(year: int) -> Date:
    # Anonymous Gregorian algorithm.
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return Date(year, month, day)


def calendar_lookup(date: str = "", region: str = "all", timezone: str = "Asia/Shanghai", task_id: str | None = None) -> str:
    """Look up Chinese lunar/fixed and common Western holidays for a date."""
    try:
        day = _parse_date(date or None, timezone=timezone or "Asia/Shanghai")
        region_value = str(region or "all").strip().lower()
        include_cn = region_value in {"all", "cn", "china", "zh", "中国"}
        include_west = region_value in {"all", "western", "west", "us", "eu", "europe", "欧美"}
        holidays: list[dict[str, Any]] = []

        if include_cn and (day.month, day.day) in _CN_GREGORIAN:
            holidays.append({
                "name": _CN_GREGORIAN[(day.month, day.day)],
                "region": "CN",
                "calendar": "gregorian",
            })

        lunar = _solar_to_lunar(day)
        if include_cn and lunar.get("supported") and not lunar.get("is_leap_month"):
            lunar_key = (int(lunar["month"]), int(lunar["day"]))
            if lunar_key in _LUNAR_HOLIDAYS:
                holidays.append({
                    "name": _LUNAR_HOLIDAYS[lunar_key],
                    "region": "CN",
                    "calendar": "chinese_lunar",
                })

        if include_west and (day.month, day.day) in _WESTERN_FIXED:
            en, zh = _WESTERN_FIXED[(day.month, day.day)]
            holidays.append({"name": zh, "name_en": en, "region": "Western", "calendar": "gregorian"})

        thanksgiving = _nth_weekday(day.year, 11, 3, 4)  # fourth Thursday
        movable = {
            _nth_weekday(day.year, 5, 6, 2): ("母亲节", "Mother's Day", "Western"),
            _nth_weekday(day.year, 6, 6, 3): ("父亲节", "Father's Day", "Western"),
            _last_weekday(day.year, 5, 0): ("美国阵亡将士纪念日", "Memorial Day", "US"),
            _nth_weekday(day.year, 9, 0, 1): ("美国劳动节", "Labor Day", "US"),
            thanksgiving: ("感恩节", "Thanksgiving", "US"),
            thanksgiving + timedelta(days=1): ("黑色星期五", "Black Friday", "US"),
            _easter_sunday(day.year): ("复活节", "Easter Sunday", "Western"),
            _easter_sunday(day.year) - timedelta(days=2): ("耶稣受难日", "Good Friday", "Western"),
        }
        if include_west and day in movable:
            zh, en, reg = movable[day]
            holidays.append({"name": zh, "name_en": en, "region": reg, "calendar": "gregorian"})

        return _json({
            "success": True,
            "date": day.isoformat(),
            "weekday_zh": _WEEKDAY_ZH[day.weekday()],
            "weekday_en": _WEEKDAY_EN[day.weekday()],
            "lunar": lunar,
            "holidays": holidays,
        })
    except Exception as exc:
        return _error(str(exc))


def _http_json(url: str, timeout: float = 10.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "Hermes-Companion-Life/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed weather/geocoding endpoints only
        raw = resp.read(1_000_000)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("weather endpoint returned non-object JSON")
    return data


def _resolve_location(location: str) -> dict[str, Any]:
    value = _safe_text(location or "成都", max_len=120) or "成都"
    key = value.lower()
    if key in _LOCATION_ALIASES:
        return dict(_LOCATION_ALIASES[key])
    if value in _LOCATION_ALIASES:
        return dict(_LOCATION_ALIASES[value])

    query = urllib.parse.urlencode({"name": value, "count": 1, "language": "zh", "format": "json"})
    data = _http_json(f"https://geocoding-api.open-meteo.com/v1/search?{query}", timeout=8.0)
    results = data.get("results") if isinstance(data.get("results"), list) else []
    if not results:
        raise ValueError(f"location not found: {value}")
    first = results[0]
    return {
        "label": _safe_text(first.get("name") or value, max_len=80),
        "country": _safe_text(first.get("country") or "", max_len=80),
        "lat": float(first["latitude"]),
        "lon": float(first["longitude"]),
        "timezone": _safe_text(first.get("timezone") or "auto", max_len=80) or "auto",
    }


def _num(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _weather_condition(code: Any) -> str:
    try:
        return _WMO_ZH.get(int(code), "天气变化")
    except Exception:
        return "天气变化"


def _period_index(period: str) -> int:
    return 1 if str(period or "today").strip().lower() == "tomorrow" else 0


def _pick_daily(daily: dict[str, Any], key: str, index: int) -> Any:
    values = daily.get(key)
    if isinstance(values, list) and len(values) > index:
        return values[index]
    return None


def _hourly_highlights(data: dict[str, Any], *, period: str, count: int = 6) -> list[dict[str, Any]]:
    raw_hourly = data.get("hourly")
    hourly: dict[str, Any] = raw_hourly if isinstance(raw_hourly, dict) else {}
    raw_times = hourly.get("time")
    raw_temps = hourly.get("temperature_2m")
    raw_pops = hourly.get("precipitation_probability")
    raw_codes = hourly.get("weather_code")
    times: list[Any] = raw_times if isinstance(raw_times, list) else []
    temps: list[Any] = raw_temps if isinstance(raw_temps, list) else []
    pops: list[Any] = raw_pops if isinstance(raw_pops, list) else []
    codes: list[Any] = raw_codes if isinstance(raw_codes, list) else []
    if not times:
        return []
    period_value = str(period or "today").lower()
    if period_value == "tonight":
        selected_hours = {18, 21, 23}
    else:
        selected_hours = {9, 12, 15, 18, 21}
    rows: list[dict[str, Any]] = []
    for idx, raw_time in enumerate(times):
        label = str(raw_time).replace("T", " ")
        try:
            hour = int(str(raw_time).split("T", 1)[1].split(":", 1)[0])
        except Exception:
            hour = -1
        if hour not in selected_hours and len(rows) >= 1:
            continue
        row: dict[str, Any] = {"time": label[-5:] if ":" in label else label, "condition": _weather_condition(codes[idx] if idx < len(codes) else None)}
        if idx < len(temps) and _num(temps[idx]) is not None:
            row["temp_c"] = _num(temps[idx])
        if idx < len(pops) and _num(pops[idx]) is not None:
            row["precip_probability_pct"] = _num(pops[idx])
        rows.append(row)
        if len(rows) >= count:
            break
    return rows


def _weather_advice(report: dict[str, Any]) -> list[str]:
    advice = []
    precipitation = report.get("precipitation")
    precip: dict[str, Any] = precipitation if isinstance(precipitation, dict) else {}
    pop = precip.get("max_probability_pct")
    amount = precip.get("amount_mm")
    try:
        if (pop is not None and float(pop) >= 40) or (amount is not None and float(amount) >= 1):
            advice.append("带伞更稳")
    except Exception:
        pass
    current_obj = report.get("temperature")
    temp: dict[str, Any] = current_obj if isinstance(current_obj, dict) else {}
    current = temp.get("current_c")
    try:
        if current is not None and float(current) >= 30:
            advice.append("注意防晒和补水")
        elif current is not None and float(current) <= 8:
            advice.append("多穿一点，别冻着")
    except Exception:
        pass
    if not advice:
        advice.append("天气总体还算省心")
    return advice[:3]


def weather_query(location: str = "成都", period: str = "today", task_id: str | None = None) -> str:
    """Query weather from fixed Open-Meteo endpoints and emit a weather.v1 rich result."""
    try:
        period_value = str(period or "today").strip().lower()
        if period_value not in {"now", "today", "tonight", "tomorrow"}:
            period_value = "today"
        loc = _resolve_location(location)
        query = urllib.parse.urlencode({
            "latitude": f"{float(loc['lat']):.5f}",
            "longitude": f"{float(loc['lon']):.5f}",
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "hourly": "temperature_2m,precipitation_probability,precipitation,weather_code,wind_speed_10m",
            "daily": "temperature_2m_min,temperature_2m_max,precipitation_sum,precipitation_probability_max",
            "timezone": loc.get("timezone") or "auto",
            "forecast_days": 2,
        })
        data = _http_json(f"https://api.open-meteo.com/v1/forecast?{query}", timeout=10.0)
        raw_current = data.get("current")
        raw_daily = data.get("daily")
        current: dict[str, Any] = raw_current if isinstance(raw_current, dict) else {}
        daily: dict[str, Any] = raw_daily if isinstance(raw_daily, dict) else {}
        index = _period_index(period_value)
        current_code = current.get("weather_code")
        condition = _weather_condition(current_code)
        min_c = _num(_pick_daily(daily, "temperature_2m_min", index))
        max_c = _num(_pick_daily(daily, "temperature_2m_max", index))
        amount = _num(_pick_daily(daily, "precipitation_sum", index))
        pop = _num(_pick_daily(daily, "precipitation_probability_max", index))
        report: dict[str, Any] = {
            "type": "weather.v1",
            "location": {
                "label": loc.get("label") or _safe_text(location, max_len=80),
                "country": loc.get("country") or "",
                "timezone": data.get("timezone") or loc.get("timezone") or "",
            },
            "period": period_value,
            "generated_at": datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"),
            "summary": f"{condition}" + (f"，{min_c:.0f}–{max_c:.0f}°C" if isinstance(min_c, (int, float)) and isinstance(max_c, (int, float)) else ""),
            "temperature": {
                "current_c": _num(current.get("temperature_2m")),
                "feels_like_c": _num(current.get("apparent_temperature")),
                "min_c": min_c,
                "max_c": max_c,
            },
            "precipitation": {
                "max_probability_pct": pop,
                "amount_mm": amount,
            },
            "wind": {"speed_kmh": _num(current.get("wind_speed_10m"))},
            "humidity_pct": _num(current.get("relative_humidity_2m")),
            "hourly_highlights": _hourly_highlights(data, period=period_value),
        }
        report["advice"] = _weather_advice(report)
        marker = f"{RICH_RESULT_BEGIN}\n{json.dumps(report, ensure_ascii=False)}\n{RICH_RESULT_END}\n"
        return _json({"success": True, "weather": report, "output": marker})
    except Exception as exc:
        return _error(str(exc))



def journal_write(
    entry: str,
    mood: str = "",
    tags: list[str] | str | None = None,
    date: str = "",
    task_id: str | None = None,
) -> str:
    """Append a diary entry to the active profile's memory palace journal."""
    try:
        from tools.memory_palace_tool import (
            _atomic_text_write,
            _check_write_mode,
            _make_backup,
            _resolve_target,
            _scan_content,
        )

        text = _safe_text(entry, max_len=4000)
        if not text:
            return _error("entry is required")
        day = _parse_date(date or None)
        path = f"journal/{day.year}/{day.strftime('%Y-%m')}.md"
        root, target, cfg = _resolve_target(path, must_exist=False)
        _check_write_mode(cfg)

        max_bytes = int(cfg.get("max_file_bytes") or 32_768)
        if target.exists():
            existing_bytes = target.stat().st_size
            if existing_bytes > max_bytes:
                return _error("journal file exceeds configured max_file_bytes", size=existing_bytes)
            content = target.read_text(encoding="utf-8", errors="replace")
            if content.strip():
                content = content.rstrip() + "\n\n"
            else:
                content = f"# Journal {day.strftime('%Y-%m')}\n\n"
        else:
            content = f"# Journal {day.strftime('%Y-%m')}\n\n"

        tag_items: list[str]
        if isinstance(tags, str):
            tag_items = [t.strip() for t in re.split(r"[,，\s]+", tags) if t.strip()]
        elif isinstance(tags, list):
            tag_items = [_safe_text(t, max_len=30) for t in tags if _safe_text(t, max_len=30)]
        else:
            tag_items = []
        mood_text = _safe_text(mood, max_len=60)
        block = [f"## {day.isoformat()} {_WEEKDAY_ZH[day.weekday()]}", "", text]
        if mood_text:
            block.extend(["", f"心情：{mood_text}"])
        if tag_items:
            block.append(f"标签：{', '.join(tag_items[:8])}")
        new_content = content + "\n".join(block).rstrip() + "\n"
        scan_error = _scan_content(new_content, cfg)
        if scan_error:
            return _error(scan_error)
        new_size = len(new_content.encode("utf-8"))
        if new_size > max_bytes:
            return _error("journal write exceeds configured max_file_bytes", size=new_size, max_file_bytes=max_bytes)
        _make_backup(target, bool(cfg.get("backups", True)))
        _atomic_text_write(target, new_content)
        return _json({"success": True, "path": target.relative_to(root).as_posix()})
    except Exception as exc:
        return _error(str(exc))


registry.register(
    name="clock_now",
    toolset="clock",
    schema={
        "description": "Get the current date and time for a named timezone. Narrow read-only clock tool; no shell/web access.",
        "parameters": {
            "type": "object",
            "properties": {"timezone": {"type": "string", "description": "IANA timezone, default Asia/Shanghai"}},
        },
    },
    handler=lambda args, **kw: clock_now(timezone=(args or {}).get("timezone", "Asia/Shanghai")),
    description="Current date/time lookup",
    emoji="🕒",
)

registry.register(
    name="calendar_lookup",
    toolset="calendar",
    schema={
        "description": "Look up Chinese lunar/common China holidays and common Western holidays for a date.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD; defaults to today in timezone"},
                "region": {"type": "string", "description": "all, cn/china, western/us/eu"},
                "timezone": {"type": "string", "description": "IANA timezone for default date"},
            },
        },
    },
    handler=lambda args, **kw: calendar_lookup(
        date=(args or {}).get("date", ""),
        region=(args or {}).get("region", "all"),
        timezone=(args or {}).get("timezone", "Asia/Shanghai"),
    ),
    description="Holiday and calendar lookup",
    emoji="📅",
)

registry.register(
    name="weather_query",
    toolset="weather",
    schema={
        "description": "Query weather via fixed weather endpoints and emit weather.v1 rich result for Feishu card rendering.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City/location, default 成都"},
                "period": {"type": "string", "enum": ["now", "today", "tonight", "tomorrow"]},
            },
        },
    },
    handler=lambda args, **kw: weather_query(
        location=(args or {}).get("location", "成都"),
        period=(args or {}).get("period", "today"),
    ),
    description="Narrow weather lookup with rich result output",
    emoji="🌦️",
)

registry.register(
    name="journal_write",
    toolset="journal",
    schema={
        "description": "Append a diary note to the active profile's memory palace journal. Uses palace write guards; not a general file tool.",
        "parameters": {
            "type": "object",
            "required": ["entry"],
            "properties": {
                "entry": {"type": "string", "description": "Diary entry text"},
                "mood": {"type": "string", "description": "Optional mood label"},
                "tags": {"description": "Optional tags as list or comma-separated text"},
                "date": {"type": "string", "description": "YYYY-MM-DD; defaults to today"},
            },
        },
    },
    handler=lambda args, **kw: journal_write(
        entry=(args or {}).get("entry", ""),
        mood=(args or {}).get("mood", ""),
        tags=(args or {}).get("tags"),
        date=(args or {}).get("date", ""),
    ),
    description="Profile palace journal appender",
    emoji="📓",
)
