from datetime import datetime
from collections import Counter
import re
import math

import pandas as pd
import numpy as np


def ordinal_day(day: int) -> str:
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def format_event_date(value) -> str:
    """Format a date as Month 1st, YYYY when possible."""
    if value is None:
        return "Unknown date"

    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw or raw.lower() == "nan":
            return "Unknown date"

        dt = None
        for pattern in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(raw, pattern)
                break
            except ValueError:
                continue

        if dt is None:
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                return raw

    human_date = f"{dt.strftime('%B')} {ordinal_day(dt.day)}, {dt.year}"
    return human_date


def parse_datetime_value(value):
    """Parse common datetime-like inputs into datetime when possible."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    raw = str(value).strip()
    if not raw or raw.lower() == "nan":
        return None

    for pattern in (
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%d %B %Y",
        "%B %d, %Y",
        "%d %b %Y",
        "%b %d, %Y",
    ):
        try:
            return datetime.strptime(raw, pattern)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_dataset_date_range(values) -> str:
    """Format a dataset date range from an iterable of date-like values."""
    parsed = [dt for dt in (parse_datetime_value(value) for value in values) if dt is not None]
    if not parsed:
        return "Unknown date range"

    start = min(parsed)
    end = max(parsed)
    return f"{format_event_date(start)} to {format_event_date(end)}"


def summarize_peak_dates(values, top_n: int = 3) -> list[dict]:
    """Return top protest dates with counts from an iterable of date-like values."""
    parsed = [dt for dt in (parse_datetime_value(value) for value in values) if dt is not None]
    if not parsed:
        return []

    counts = Counter(dt.strftime("%Y-%m-%d") for dt in parsed)
    peaks = counts.most_common(top_n)
    return [
        {
            "date": iso_date,
            "formatted_date": format_event_date(iso_date),
            "count": count,
        }
        for iso_date, count in peaks
    ]


def peak_dates_to_text(peak_dates: list[dict], empty_label: str = "No peak dates available.") -> str:
    """Format peak-date summary as readable text."""
    if not peak_dates:
        return empty_label
    return "; ".join(f"{item['formatted_date']} ({item['count']} protests)" for item in peak_dates)


STOPWORDS = {
    "the", "and", "for", "that", "with", "from", "were", "was", "this", "have", "has", "had", "their",
    "they", "them", "into", "after", "during", "about", "over", "under", "more", "than", "into", "while",
    "said", "says", "according", "against", "there", "would", "could", "should", "been", "being", "also",
    "to", "by", "in", "of", "an", "at",
    "women", "woman", "protest", "protests", "group", "groups", "people",
    "march", "marches", "demonstration", "demonstrators", "supporters", "activists", "community",
    "government", "local", "state", "country", "cities", "city", "notes", "event",
    "events", "said", "near", "around", "across", "reported", "reportedly", "including", "demanded",
    "mujeres", "mujer", "para", "como", "sobre", "esta", "este", "dijo", "ante", "desde", "entre", "la"
}


def extract_word_frequencies(df, top_n: int = 40) -> list[tuple[str, int]]:
    """Extract word frequencies from notes and related text for word-cloud style visualization."""
    if df is None or df.empty:
        return []

    text_columns = [
        col for col in ["notes", "actor1", "assoc_actor_1", "actor2", "assoc_actor_2", "location", "admin1", "admin2"]
        if col in df.columns
    ]
    if not text_columns:
        return []

    text = " ".join(
        " ".join(df[col].dropna().astype(str).tolist())
        for col in text_columns
    ).lower()
    tokens = re.findall(r"\b[a-záéíóúñü0-9]{1,}\b", text, flags=re.IGNORECASE)
    words = [token for token in tokens if token.lower() not in STOPWORDS]
    return Counter(words).most_common(top_n)


def compute_time_series_metrics(timeline_data: pd.DataFrame) -> dict:
    """Compute summary metrics for the women's protest time series."""
    empty = {
        "women_protest_share": None,
        "trend_slope": None,
        "trend_label": "Insufficient data",
        "pattern_label": "Insufficient data",
        "volatility": None,
        "peak_concentration": None,
        "pearson_correlation": None,
    }
    if timeline_data is None or timeline_data.empty or "Women's Mobilizations" not in timeline_data.columns:
        return empty

    women = timeline_data["Women's Mobilizations"].fillna(0).astype(float)
    if "Other Protests" in timeline_data.columns:
        other = timeline_data["Other Protests"].fillna(0).astype(float)
    else:
        other = pd.Series(0.0, index=women.index)
    total = women + other

    women_sum = float(women.sum())
    total_sum = float(total.sum())
    women_protest_share = (women_sum / total_sum) if total_sum > 0 else None

    if len(women) >= 2:
        x = np.arange(len(women), dtype=float)
        trend_slope = float(np.polyfit(x, women.to_numpy(), 1)[0])
    else:
        trend_slope = None

    mean_women = float(women.mean()) if len(women) > 0 else 0.0
    std_women = float(women.std(ddof=0)) if len(women) > 0 else 0.0
    volatility = (std_women / mean_women) if mean_women > 0 else None
    peak_concentration = (float(women.max()) / women_sum) if women_sum > 0 else None

    if len(women) >= 2 and women.std(ddof=0) > 0 and total.std(ddof=0) > 0:
        pearson_correlation = float(np.corrcoef(women.to_numpy(), total.to_numpy())[0, 1])
    else:
        pearson_correlation = None

    trend_label = "Stable"
    if trend_slope is not None:
        if trend_slope > 0.35:
            trend_label = "Increasing"
        elif trend_slope < -0.35:
            trend_label = "Decreasing"

    pattern_label = "Regular"
    if volatility is not None and peak_concentration is not None:
        if women_sum <= 6 or peak_concentration > 0.6:
            pattern_label = "Sparse"
        elif volatility > 1.0 or peak_concentration > 0.45:
            pattern_label = "Intermittent"
        elif volatility > 0.65:
            pattern_label = "Volatile"

    return {
        "women_protest_share": women_protest_share,
        "trend_slope": trend_slope,
        "trend_label": trend_label,
        "pattern_label": pattern_label,
        "volatility": volatility,
        "volatility_label": (
            "Very low" if volatility is not None and volatility < 0.30 else
            "Moderate" if volatility is not None and volatility < 0.60 else
            "High" if volatility is not None and volatility < 1.00 else
            "Very high" if volatility is not None else
            "N/A"
        ),
        "peak_concentration": peak_concentration,
        "pearson_correlation": pearson_correlation,
    }
