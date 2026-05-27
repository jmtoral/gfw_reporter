import streamlit as st
import pandas as pd
import os
import hashlib
import math
from collections import Counter
from dotenv import load_dotenv
from datetime import datetime

from src.data_processor import get_available_countries, filter_by_country, get_women_mobilizations, get_other_relevant_protests
from src.llm_engine import summarize_events_for_llm, generate_report_text, get_model_name
from src.pdf_generator import generate_pdf_bytes
from src.docx_generator import generate_docx_bytes
from src.report_storage import save_report_bundle
from src.utils import (
    format_dataset_date_range,
    summarize_peak_dates,
    peak_dates_to_text,
    parse_datetime_value,
    extract_word_frequencies,
    compute_time_series_metrics,
)

load_dotenv()

RESULT_SCHEMA_VERSION = 2

if "report_result" not in st.session_state:
    st.session_state.report_result = None

if "save_message" not in st.session_state:
    st.session_state.save_message = None

if "usage_history" not in st.session_state:
    st.session_state.usage_history = []


def extract_first_markdown_table(markdown_text: str):
    lines = markdown_text.splitlines()
    start_idx = None
    end_idx = None
    table_lines = []

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            if start_idx is None:
                start_idx = idx
            table_lines.append(stripped)
            end_idx = idx
        elif start_idx is not None:
            break

    if start_idx is None or len(table_lines) < 2:
        return None

    header = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    rows = []
    for line in table_lines[1:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if all(set(cell.replace(" ", "")) <= {"-", ":"} for cell in cells):
            continue
        padded = cells + [""] * (len(header) - len(cells))
        rows.append(padded[: len(header)])

    if not rows:
        return None

    df = pd.DataFrame(rows, columns=header)
    return {
        "start_idx": start_idx,
        "end_idx": end_idx,
        "dataframe": df,
    }


def dataframe_to_markdown_table(df: pd.DataFrame) -> list[str]:
    columns = list(df.columns)
    table_lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in df.fillna("").iterrows():
        values = [str(row[col]).replace("\n", " ").strip() for col in columns]
        table_lines.append("| " + " | ".join(values) + " |")
    return table_lines


def sort_contact_table(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    sorted_df = df.copy()
    for col in sorted_df.columns:
        sorted_df[col] = sorted_df[col].fillna("").astype(str).str.strip()

    def has_real_value(series: pd.Series, placeholders: set[str]) -> pd.Series:
        lowered = series.str.lower()
        return (~lowered.isin(placeholders)) & lowered.ne("")

    org_col = "Organization" if "Organization" in sorted_df.columns else sorted_df.columns[0]
    geo_col = "Geography" if "Geography" in sorted_df.columns else None
    contact_col = "Contact" if "Contact" in sorted_df.columns else None

    placeholder_contacts = {"not provided in acled data", "not provided", "unknown", ""}
    placeholder_geo = {"not specified in acled data", "unknown location", "unknown", ""}

    sorted_df["_has_contact"] = has_real_value(sorted_df[contact_col], placeholder_contacts) if contact_col else False
    sorted_df["_has_geo"] = has_real_value(sorted_df[geo_col], placeholder_geo) if geo_col else False
    sorted_df["_org_sort"] = sorted_df[org_col].str.lower()

    sorted_df = sorted_df.sort_values(
        by=["_has_contact", "_has_geo", "_org_sort"],
        ascending=[False, False, True],
        kind="stable",
    ).drop(columns=["_has_contact", "_has_geo", "_org_sort"])

    return sorted_df.reset_index(drop=True)


def replace_first_markdown_table(markdown_text: str, df: pd.DataFrame) -> str:
    parsed = extract_first_markdown_table(markdown_text)
    if not parsed:
        return markdown_text

    lines = markdown_text.splitlines()
    new_lines = (
        lines[: parsed["start_idx"]]
        + dataframe_to_markdown_table(df)
        + lines[parsed["end_idx"] + 1 :]
    )
    return "\n".join(new_lines)


METRIC_CARD_CSS = """
<style>
.metric-card-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin-top: 12px;
    margin-bottom: 8px;
}
.metric-card {
    border: 1px solid #ece7ef;
    border-radius: 14px;
    padding: 14px 16px;
    background: #faf8fb;
    box-shadow: 0 1px 6px rgba(65,19,66,0.04);
}
.metric-card-label {
    font-size: 0.85rem;
    color: #6d6170;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 6px;
}
.metric-card-value {
    font-size: 1.35rem;
    font-weight: 700;
    color: #411342;
    line-height: 1.2;
}
.metric-card-info {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    border-radius: 999px;
    font-size: 0.7rem;
    font-weight: 700;
    color: #6d6170;
    cursor: help;
    background: rgba(65,19,66,0.06);
}
</style>
"""

ACTION_BAR_CSS = """
<style>
.action-bar {
    margin-top: 16px;
    margin-bottom: 10px;
    padding: 14px 16px;
    border: 1px solid #ece7ef;
    border-radius: 14px;
    background: #faf8fb;
}
</style>
"""

SUMMARY_BAR_CSS = """
<style>
.summary-card-grid {
    display: grid;
    grid-template-columns: 1.2fr 1fr 1fr;
    gap: 16px;
    margin-top: 8px;
    margin-bottom: 16px;
}
.summary-card {
    border: 1px solid #ece7ef;
    border-radius: 16px;
    background: #faf8fb;
    box-shadow: 0 1px 6px rgba(65,19,66,0.04);
    padding: 14px 16px;
}
.summary-card-label {
    font-size: 0.8rem;
    color: #6d6170;
    margin-bottom: 6px;
}
.summary-card-value {
    font-size: 1.02rem;
    font-weight: 700;
    color: #411342;
    line-height: 1.35;
}
</style>
"""


def collapse_bullets_to_paragraphs(text: str) -> str:
    lines = text.splitlines()
    result = []
    bullet_buffer = []

    def flush_bullets():
        nonlocal bullet_buffer
        if bullet_buffer:
            result.append(" ".join(item.rstrip(".") + "." for item in bullet_buffer))
            bullet_buffer = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            bullet_buffer.append(stripped[2:].strip())
            continue
        flush_bullets()
        result.append(line)

    flush_bullets()
    return "\n".join(result)


def build_python_metrics_report(result):
    women_peaks = result.get("women_peak_dates", [])
    overall_peaks = result.get("overall_peak_dates", [])
    women_peaks_text = peak_dates_to_text(women_peaks, "No peak dates available.")
    overall_peaks_text = peak_dates_to_text(overall_peaks, "No peak dates available.")
    if result["analysis_skill"] == "Women and Gender Focus":
        return f"""## 1. Protest Dynamics Around Gender and Intersectional Agendas

Dataset range: {result['date_range']}

This Python-only report mode summarizes structured protest metrics without LLM-generated interpretation. In the selected date range, {result['women_events_count']} women's protests and {result['other_events_count']} other protests were recorded. The dates with the highest women's protest activity were {women_peaks_text}. The dates with the highest protest activity overall were {overall_peaks_text}.

## 2. Broader Civil Society and Media Trends

No AI narrative was generated in this mode. If additional context was provided by the user, it should be interpreted as supporting notes rather than automatically synthesized findings.

## 3. Potential Actors Connected to Most Salient Issue/s

| Organization | Focus Area | Geography | Contact |
| --- | --- | --- | --- |
| Python metrics mode | Structured event counts only | Not specified in ACLED data | Not provided in ACLED data |
"""

    return f"""## Executive Summary

Dataset range: {result['date_range']}

This Python-only report mode summarizes structured protest metrics without LLM-generated interpretation. In the selected date range, {result['women_events_count']} women's protests and {result['other_events_count']} other protests were recorded. The peak dates for women's protests were {women_peaks_text}. The peak dates for all protests were {overall_peaks_text}.

## Organizations Involved

This Python-only mode keeps the report focused on computed metrics and visual summaries.

## Main Themes

No AI-generated thematic interpretation was produced in this mode.
"""


def render_report_result(result):
    st.write("---")
    st.markdown(SUMMARY_BAR_CSS, unsafe_allow_html=True)
    summary_html = f"""
    <div class="summary-card-grid">
        <div class="summary-card">
            <div class="summary-card-label">Dataset date range</div>
            <div class="summary-card-value">{result['date_range']}</div>
        </div>
        <div class="summary-card">
            <div class="summary-card-label">Peak date(s): Women</div>
            <div class="summary-card-value">{peak_dates_to_text(result["women_peak_dates"], "No peak dates available.")}</div>
        </div>
        <div class="summary-card">
            <div class="summary-card-label">Peak date(s): Overall</div>
            <div class="summary-card-value">{peak_dates_to_text(result["overall_peak_dates"], "No peak dates available.")}</div>
        </div>
    </div>
    """
    st.markdown(summary_html, unsafe_allow_html=True)
    st.subheader("📊 Data Visualization")

    st.markdown("#### Temporal Evolution")
    if result["timeline_data"] is not None:
        import altair as alt

        metrics_source = result.get("timeline_metrics_data") if result.get("timeline_metrics_data") is not None else result["timeline_data"]
        metrics = result.get("time_series_metrics") or compute_time_series_metrics(metrics_source)
        share = metrics.get("women_protest_share")
        volatility = metrics.get("volatility")
        volatility_label = metrics.get("volatility_label", "N/A")
        concentration = metrics.get("peak_concentration")
        correlation = metrics.get("pearson_correlation")

        timeline_df = result["timeline_data"].reset_index()
        first_column = timeline_df.columns[0]
        timeline_df = timeline_df.rename(columns={first_column: "Date"})
        timeline_df["DateLabel"] = pd.to_datetime(timeline_df["Date"]).dt.strftime("%B %d, %Y")
        series_columns = [col for col in timeline_df.columns if col in ["Women's Mobilizations", "Other Protests"]]
        timeline_long = timeline_df.melt(
            id_vars=["Date", "DateLabel"],
            value_vars=series_columns,
            var_name="Series",
            value_name="Protests",
        )
        timeline_long["DateLabel"] = pd.to_datetime(timeline_long["Date"]).dt.strftime("%B %d, %Y")
        chart = alt.Chart(timeline_long).mark_line(
            strokeWidth=2,
            point=alt.OverlayMarkDef(size=36, filled=True),
        ).encode(
            x=alt.X(
                "Date:T",
                title="Date (daily)",
                axis=alt.Axis(format="%b %d", labelAngle=-35),
            ),
            y=alt.Y("Protests:Q", title="Protests"),
            color=alt.Color(
                "Series:N",
                scale=alt.Scale(
                    domain=["Women's Mobilizations", "Other Protests"],
                    range=["#d228f4", "#411342"],
                ),
                title="Series",
            ),
            tooltip=[
                alt.Tooltip("DateLabel:N", title="Date"),
                alt.Tooltip("Series:N", title="Series"),
                alt.Tooltip("Protests:Q", title="Protests"),
            ],
        ).properties(height=320)
        st.altair_chart(chart.interactive(), use_container_width=True)
        st.caption("Daily counts with day-level hover.")

        st.markdown(METRIC_CARD_CSS, unsafe_allow_html=True)
        metric_cards_html = f"""
        <div class="metric-card-grid">
            <div class="metric-card">
                <div class="metric-card-label">Women protest share <span class="metric-card-info" title="Share of women’s mobilizations out of all protests included in the selected period.">i</span></div>
                <div class="metric-card-value">{f"{share:.1%}" if share is not None else "N/A"}</div>
            </div>
            <div class="metric-card">
                <div class="metric-card-label">Trend <span class="metric-card-info" title="Direction of the monthly women’s protest series based on the fitted slope: increasing, stable, or decreasing.">i</span></div>
                <div class="metric-card-value">{metrics.get("trend_label", "N/A")}</div>
            </div>
            <div class="metric-card">
                <div class="metric-card-label">Pattern <span class="metric-card-info" title="Simple qualitative reading of the series shape. Sparse suggests relatively few events or a series concentrated in a small number of months.">i</span></div>
                <div class="metric-card-value">{metrics.get("pattern_label", "N/A")}</div>
            </div>
            <div class="metric-card">
                <div class="metric-card-label">Monthly variation <span class="metric-card-info" title="How uneven the monthly women’s protest counts are across the selected period. It is based on the coefficient of variation (standard deviation divided by mean). It has no fixed upper bound: 0 means all months are equal, and higher values mean more fluctuation. This card shows a qualitative label instead of the raw number.">i</span></div>
                <div class="metric-card-value">{volatility_label}{f" ({volatility:.2f})" if volatility is not None else ""}</div>
            </div>
            <div class="metric-card">
                <div class="metric-card-label">Peak concentration <span class="metric-card-info" title="Share of all women’s protests concentrated in the single highest month. Higher values mean activity is more concentrated in one peak.">i</span></div>
                <div class="metric-card-value">{f"{concentration:.1%}" if concentration is not None else "N/A"}</div>
            </div>
            <div class="metric-card">
                <div class="metric-card-label">Pearson correlation <span class="metric-card-info" title="Linear correlation between the monthly women’s protest series and the monthly total protest series. Values closer to 1 indicate they move together more closely.">i</span></div>
                <div class="metric-card-value">{f"{correlation:.2f}" if correlation is not None else "N/A"}</div>
            </div>
        </div>
        """
        st.markdown(metric_cards_html, unsafe_allow_html=True)
    else:
        st.warning("Could not generate timeline due to date format issues.")

    st.markdown("#### Word Clouds")
    col_wc1, col_wc2 = st.columns(2)
    with col_wc1:
        st.markdown("**Women's Mobilizations**")
        render_word_cloud(result.get("women_word_frequencies", []), color="#d228f4")
    with col_wc2:
        st.markdown("**Other Protests**")
        render_word_cloud(result.get("other_word_frequencies", []), color="#411342")

    st.markdown("#### Top Actors and Geographies")
    import altair as alt

    def render_bar_chart(items, label_column, color):
        df_items = pd.DataFrame(items, columns=[label_column, "Frequency"])
        chart = alt.Chart(df_items).mark_bar(color=color).encode(
            x=alt.X("Frequency:Q", title="Frequency"),
            y=alt.Y(f"{label_column}:N", sort="-x", title="")
        ).properties(height=350)
        st.altair_chart(chart, use_container_width=True)

    col_actor1, col_actor2 = st.columns(2)
    with col_actor1:
        st.markdown("**Top Actors in Women's Mobilizations**")
        if result["actor_w"]:
            render_bar_chart(result["actor_w"], "Actor", "#d228f4")
        else:
            st.info("Not enough data.")

    with col_actor2:
        st.markdown("**Top Actors in Other Protests**")
        if result["actor_o"]:
            render_bar_chart(result["actor_o"], "Actor", "#411342")
        else:
            st.info("Not enough data.")

    col_geo1, col_geo2 = st.columns(2)
    with col_geo1:
        st.markdown("**Top Geographies in Women's Mobilizations**")
        if result["geo_w"]:
            render_bar_chart(result["geo_w"], "Geography", "#d228f4")
        else:
            st.info("Not enough data.")

    with col_geo2:
        st.markdown("**Top Geographies in Other Protests**")
        if result["geo_o"]:
            render_bar_chart(result["geo_o"], "Geography", "#411342")
        else:
            st.info("Not enough data.")

    st.markdown("#### Geographical Distribution")
    if result["map_data"] is not None and not result["map_data"].empty:
        import pydeck as pdk
        map_points = result["map_data"].copy()
        st.pydeck_chart(pdk.Deck(
            map_style='light',
            initial_view_state=pdk.ViewState(
                latitude=map_points['latitude'].mean(),
                longitude=map_points['longitude'].mean(),
                zoom=6.5,
                pitch=0,
            ),
            layers=[
                pdk.Layer(
                    "ScatterplotLayer",
                    data=map_points,
                    get_position='[longitude, latitude]',
                    get_radius='radius',
                    get_color='[210, 40, 244, 180]',
                    pickable=True,
                    auto_highlight=True,
                ),
            ],
            tooltip={
                "html": "<b>Location</b>: {location_name}<br/><b>Registered protests</b>: {protest_count}",
                "style": {
                    "backgroundColor": "#411342",
                    "color": "white",
                },
            },
        ))
    elif result["map_available"]:
        st.warning("No coordinate data available for selected filters.")
    else:
        st.warning("Coordinates not found in the file.")

    st.write("---")
    st.subheader("Report Draft")
    final_report_text = result["report_text"]
    parsed_table = extract_first_markdown_table(result["report_text"])
    if parsed_table and "Contact" in parsed_table["dataframe"].columns:
        st.markdown("#### Review Contacts Before PDF")
        st.caption("Edit the table below before generating the final PDF. The PDF and local save will use this updated version.")
        editor_key = f"contact_editor_{result['file_signature']}_{result['country']}_{result['analysis_skill']}"
        editable_df = sort_contact_table(parsed_table["dataframe"])
        edited_df = st.data_editor(
            editable_df,
            use_container_width=True,
            hide_index=True,
            key=editor_key,
        )
        final_report_text = replace_first_markdown_table(result["report_text"], sort_contact_table(edited_df))

    st.markdown(final_report_text)

    usage = result.get("usage")
    if usage:
        st.markdown("#### LLM Usage")
        col_u1, col_u2, col_u3, col_u4 = st.columns(4)
        col_u1.metric("Input tokens", usage["input_tokens"] if usage["input_tokens"] is not None else "N/A")
        col_u2.metric("Output tokens", usage["output_tokens"] if usage["output_tokens"] is not None else "N/A")
        col_u3.metric("Total tokens", usage["total_tokens"] if usage["total_tokens"] is not None else "N/A")
        col_u4.metric("Latency (s)", usage["latency_seconds"])

        estimated_cost = usage.get("estimated_cost_usd")
        if estimated_cost is not None:
            st.caption(f"Estimated cost: `${estimated_cost:.6f} USD`")
            st.caption("Note: this is an approximate estimate based on hardcoded official pricing references and may drift if providers update rates.")
        else:
            st.caption("Estimated cost: not configured for this model.")

    current_pdf_bytes = generate_pdf_bytes(result["country"], final_report_text, date_range=result.get("date_range"))
    current_docx_bytes = generate_docx_bytes(result["country"], final_report_text, date_range=result.get("date_range"))
    docx_name = result.get("docx_name")
    if not docx_name:
        pdf_name = result.get("pdf_name", "Report.docx")
        docx_name = pdf_name[:-4] + ".docx" if pdf_name.lower().endswith(".pdf") else "Report.docx"
    st.markdown(ACTION_BAR_CSS, unsafe_allow_html=True)
    st.markdown('<div class="action-bar">', unsafe_allow_html=True)
    st.markdown("#### Export Options")
    st.caption("Download the final report in PDF or Word format, or save the full bundle locally.")
    col_download1, col_download2, col_download3 = st.columns(3)
    with col_download1:
        st.download_button(
            label="📄 Download PDF Report",
            data=current_pdf_bytes,
            file_name=result["pdf_name"],
            mime="application/pdf",
        )
    with col_download2:
        st.download_button(
            label="📝 Download Word Report",
            data=current_docx_bytes,
            file_name=docx_name,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    with col_download3:
        if st.button("💾 Save Results Locally", use_container_width=True):
            save_payload = dict(result)
            save_payload["report_text"] = final_report_text
            save_payload["pdf_bytes"] = current_pdf_bytes
            save_payload["docx_bytes"] = current_docx_bytes
            save_payload["docx_name"] = docx_name
            saved_path = save_report_bundle(save_payload)
            st.session_state.save_message = f"Saved report bundle to `{saved_path}`."
    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.save_message:
        st.success(st.session_state.save_message)


def render_usage_dashboard():
    st.sidebar.markdown("---")
    st.sidebar.subheader("Usage Dashboard")

    history = st.session_state.usage_history
    if not history:
        st.sidebar.caption("No LLM runs recorded yet.")
        return

    total_runs = len(history)
    total_input = sum(item.get("input_tokens") or 0 for item in history)
    total_output = sum(item.get("output_tokens") or 0 for item in history)
    total_tokens = sum(item.get("total_tokens") or 0 for item in history)
    total_cost = sum(item.get("estimated_cost_usd") or 0 for item in history)

    st.sidebar.metric("Runs", total_runs)
    st.sidebar.metric("Total tokens", total_tokens)
    st.sidebar.caption(f"Input tokens: {total_input} | Output tokens: {total_output}")
    if any(item.get("estimated_cost_usd") is not None for item in history):
        st.sidebar.caption(f"Estimated total cost: `${total_cost:.6f} USD`")
        st.sidebar.caption("Approximate values based on hardcoded pricing references.")
    else:
        st.sidebar.caption("Estimated cost unavailable until pricing is configured.")

    dashboard_rows = []
    for item in reversed(history[-10:]):
        dashboard_rows.append({
            "timestamp": item.get("timestamp"),
            "country": item.get("country"),
            "provider": item.get("provider"),
            "model": item.get("model_name"),
            "skill": item.get("analysis_skill"),
            "input_tokens": item.get("input_tokens"),
            "output_tokens": item.get("output_tokens"),
            "total_tokens": item.get("total_tokens"),
            "latency_seconds": item.get("latency_seconds"),
            "estimated_cost_usd": item.get("estimated_cost_usd"),
        })

    st.sidebar.dataframe(pd.DataFrame(dashboard_rows), use_container_width=True, hide_index=True)


def render_word_cloud(word_frequencies, color: str):
    if not word_frequencies:
        st.info("Not enough note text for a word cloud.")
        return

    import matplotlib.pyplot as plt
    import numpy as np

    if len(word_frequencies) < 8:
        fallback_df = pd.DataFrame(word_frequencies, columns=["Word", "Frequency"])
        st.caption("Showing top words instead of a full word cloud because the available note text is limited.")
        st.dataframe(fallback_df, use_container_width=True, hide_index=True)
        return

    fig, ax = plt.subplots(figsize=(7, 4.8))
    ax.axis("off")
    max_freq = max(freq for _, freq in word_frequencies)
    rng = np.random.default_rng(42)
    placed_boxes = []

    def overlaps(box_a, box_b):
        ax1, ay1, ax2, ay2 = box_a
        bx1, by1, bx2, by2 = box_b
        return not (ax2 < bx1 or bx2 < ax1 or ay2 < by1 or by2 < ay1)

    def estimate_box(x, y, word, size):
        width = min(0.34, 0.0018 * size * max(len(word), 2))
        height = min(0.11, 0.0046 * size)
        return (x - width / 2, y - height / 2, x + width / 2, y + height / 2)

    for idx, (word, freq) in enumerate(word_frequencies):
        size = 8 + (freq / max_freq) * 16
        alpha = 0.55 + (freq / max_freq) * 0.45
        chosen_position = None

        if idx == 0:
            candidates = [(0.5, 0.52)]
        else:
            candidates = []
            for step in range(1, 90):
                angle = step * 0.85 + idx * 0.45 + rng.uniform(-0.08, 0.08)
                radius = min(0.44, 0.06 + 0.011 * step + 0.018 * math.sqrt(idx))
                x = 0.5 + radius * math.cos(angle)
                y = 0.5 + radius * math.sin(angle) * 0.83
                x = min(max(x, 0.08), 0.92)
                y = min(max(y, 0.10), 0.90)
                candidates.append((x, y))

        for x, y in candidates:
            box = estimate_box(x, y, word, size)
            if box[0] < 0.03 or box[2] > 0.97 or box[1] < 0.05 or box[3] > 0.95:
                continue
            if any(overlaps(box, existing) for existing in placed_boxes):
                continue
            chosen_position = (x, y, box)
            break

        if chosen_position is None:
            x, y = candidates[min(len(candidates) - 1, idx % len(candidates))]
            box = estimate_box(x, y, word, size)
            chosen_position = (x, y, box)

        x, y, box = chosen_position
        placed_boxes.append(box)
        ax.text(
            x,
            y,
            word,
            fontsize=size,
            color=color,
            alpha=alpha,
            ha="center",
            va="center",
            transform=ax.transAxes,
        )

    st.pyplot(fig, clear_figure=True)

st.set_page_config(page_title="GFW Analysis App", layout="wide")

# Custom CSS for Accents
st.markdown("""
<style>
/* Accent Color 1: #e1f977 (e.g., secondary text, highlights) */
/* Accent Color 2: #d228f4 (e.g., hover effects, progress bars) */

.stButton > button {
    border-color: #d228f4;
    transition: all 0.3s ease;
}
.stButton > button:hover {
    border-color: #e1f977;
    color: #411342;
    background-color: #e1f977;
}
div.stSpinner > div > div {
    border-top-color: #d228f4 !important;
}
[data-testid="stFileUploader"] section {
    border-color: #e1f977 !important;
}
[data-testid="stFileUploader"] section:hover {
    border-color: #e1f977 !important;
}
[data-testid="stFileUploaderDropzone"] {
    border-color: #e1f977 !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] small {
    color: #411342 !important;
}
</style>
""", unsafe_allow_html=True)

# Sidebar Configuration
st.sidebar.markdown(
    '<div style="text-align: center; margin-bottom: 20px;">'
    '<img src="https://www.globalfundforwomen.org/wp-content/themes/gffw-theme/img/logo-footer.svg" width="200" />'
    '</div>',
    unsafe_allow_html=True
)

st.sidebar.title("⚙️ Configuration")

st.sidebar.markdown("**Analysis Skill**")
analysis_skill = st.sidebar.selectbox(
    "Analysis Skill",
    ["Women and Gender Focus", "General"],
    help="Choose the analytical lens used to draft the report.",
    label_visibility="collapsed",
)

if analysis_skill == "Women and Gender Focus":
    st.sidebar.info(
        "This skill prioritizes women-led mobilizations, gender dynamics, risks, "
        "rights claims, and protection concerns grounded in the event notes."
    )

st.sidebar.markdown("**Reporting Mode**")
ai_report_mode = st.sidebar.toggle(
    "AI Report Mode",
    value=True,
    help="Turn this on to generate an AI-written report. Turn it off to keep only Python-calculated metrics.",
)
report_mode = "LLM report" if ai_report_mode else "Python metrics only"

st.sidebar.markdown("**AI Provider**")
llm_provider = st.sidebar.selectbox(
    "Select AI Provider",
    ["OpenAI", "Anthropic", "Gemini"],
    label_visibility="collapsed",
)
model_name = get_model_name(llm_provider)
st.sidebar.caption(f"Model in use: `{model_name}`")

api_key_input = st.sidebar.text_input(
    f"{llm_provider} API Key", 
    type="password", 
    help=f"Enter your {llm_provider} key to enable text generation."
)

if api_key_input:
    if llm_provider == "OpenAI":
        os.environ["OPENAI_API_KEY"] = api_key_input
    elif llm_provider == "Anthropic":
        os.environ["ANTHROPIC_API_KEY"] = api_key_input
    elif llm_provider == "Gemini":
        os.environ["GEMINI_API_KEY"] = api_key_input

render_usage_dashboard()

st.title("Event Source Reporter")
st.markdown(
    "Upload a structured event CSV to filter records, generate AI analysis, and download a PDF report."
)
st.caption(
    f"Current model: `{model_name}` | Current analysis skill: `{analysis_skill}` | Current report mode: `{report_mode}`"
)

# File uploader
uploaded_file = st.file_uploader("Upload source CSV file", type=["csv"])

if uploaded_file is not None:
    # Load data
    with st.spinner("Loading data..."):
        try:
            uploaded_bytes = uploaded_file.getvalue()
            file_signature = hashlib.md5(uploaded_bytes).hexdigest()
            df = pd.read_csv(uploaded_file)
            st.success(f"File loaded successfully. {len(df)} records found.")
        except Exception as e:
            st.error(f"Error reading file: {e}")
            st.stop()
            
    # Country selection
    countries = get_available_countries(df)
    if not countries:
        st.warning("The 'country' column was not found in the CSV.")
        st.stop()
        
    selected_country = st.selectbox("Select a country for analysis", ["-- Select --"] + countries)
    
    if selected_country != "-- Select --":
        additional_context = st.text_area(
            "Additional context for the report",
            height=180,
            placeholder=(
                "Paste optional newspaper notes, NGO summaries, field observations, or other contextual text here. "
                "This will be used as secondary context for the report."
            ),
            help="Optional free-text context that complements the structured event data.",
        )
        st.caption(
            "Recommended: paste plain text, include source names when useful, separate notes with blank lines, "
            "and keep the content focused on the selected country and time period."
        )
        st.caption(
            "Limitations: very long notes increase token usage and cost, mixed countries or time periods reduce precision, "
            "URLs alone are usually not enough, and the app does not validate source quality for you."
        )

        if st.button("Generate Analysis and Report"):
            # Check for API Key
            if report_mode == "LLM report" and not os.getenv(f"{llm_provider.upper()}_API_KEY"):
                st.error(f"⚠️ Please enter your {llm_provider} API Key in the left sidebar before continuing.")
                st.stop()
                
            with st.spinner("Filtering data..."):
                df_country = filter_by_country(df, selected_country)
                date_range = format_dataset_date_range(df_country["event_date"]) if "event_date" in df_country.columns else "Unknown date range"
                
                # Women mobilizations
                df_women = get_women_mobilizations(df_country)
                
                # Other protests
                df_other = get_other_relevant_protests(df_country, exclude_indices=df_women.index)
                df_total_protests = pd.concat([df_women, df_other]).sort_index()
                df_total_protests = df_total_protests[~df_total_protests.index.duplicated(keep="first")]
                women_peak_dates = summarize_peak_dates(df_women["event_date"]) if "event_date" in df_women.columns else []
                overall_peak_dates = summarize_peak_dates(df_total_protests["event_date"]) if "event_date" in df_total_protests.columns else []

                summary_women = summarize_events_for_llm(df_women)
                summary_other = summarize_events_for_llm(df_other)

                timeline_data = None
                timeline_metrics_data = None
            try:
                df_w_time = df_women.copy()
                df_w_time["Fecha"] = df_w_time["event_date"].apply(parse_datetime_value)
                df_w_time = df_w_time.dropna(subset=["Fecha"])
                ts_w_daily = (
                    df_w_time.groupby(df_w_time["Fecha"].apply(lambda x: x.replace(hour=0, minute=0, second=0, microsecond=0)))
                    .size()
                    .rename("Women's Mobilizations")
                )
                ts_w_monthly = (
                    df_w_time.groupby(df_w_time["Fecha"].apply(lambda x: x.replace(day=1, hour=0, minute=0, second=0, microsecond=0)))
                    .size()
                    .rename("Women's Mobilizations")
                )
                
                df_o_time = df_other.copy()
                df_o_time["Fecha"] = df_o_time["event_date"].apply(parse_datetime_value)
                df_o_time = df_o_time.dropna(subset=["Fecha"])
                ts_o_daily = (
                    df_o_time.groupby(df_o_time["Fecha"].apply(lambda x: x.replace(hour=0, minute=0, second=0, microsecond=0)))
                    .size()
                    .rename("Other Protests")
                )
                ts_o_monthly = (
                    df_o_time.groupby(df_o_time["Fecha"].apply(lambda x: x.replace(day=1, hour=0, minute=0, second=0, microsecond=0)))
                    .size()
                    .rename("Other Protests")
                )

                timeline_data = pd.concat([ts_w_daily, ts_o_daily], axis=1).fillna(0)
                if not timeline_data.empty:
                    full_daily_index = pd.date_range(
                        start=timeline_data.index.min(),
                        end=timeline_data.index.max(),
                        freq="D",
                    )
                    timeline_data = timeline_data.reindex(full_daily_index, fill_value=0)
                    timeline_data.index.name = "Date"
                timeline_metrics_data = pd.concat([ts_w_monthly, ts_o_monthly], axis=1).fillna(0)
            except Exception as e:
                timeline_data = None
                timeline_metrics_data = None

            def get_top_values(df_subset, candidate_columns, max_items=10):
                values = []
                for col in candidate_columns:
                    if col in df_subset.columns:
                        series = df_subset[col].dropna().astype(str).str.strip()
                        series = series[series.ne("") & series.ne("nan")]
                        values.extend(series.tolist())
                return Counter(values).most_common(max_items)

            actor_columns = ["actor1", "assoc_actor_1", "actor2", "assoc_actor_2"]
            geography_columns = ["location", "admin2", "admin1"]
            actor_w = get_top_values(df_women, actor_columns)
            actor_o = get_top_values(df_other, actor_columns)
            geo_w = get_top_values(df_women, geography_columns)
            geo_o = get_top_values(df_other, geography_columns)
            women_word_frequencies = extract_word_frequencies(df_women)
            other_word_frequencies = extract_word_frequencies(df_other)
            time_series_metrics = compute_time_series_metrics(timeline_metrics_data)

            map_available = 'latitude' in df.columns and 'longitude' in df.columns
            map_data = None
            if map_available:
                def build_map_frame(subset, women_flag):
                    if not {'latitude', 'longitude'}.issubset(subset.columns):
                        return None
                    frame = subset.copy()
                    if "location" in frame.columns:
                        frame["location_name"] = frame["location"].fillna("Unknown location").astype(str)
                    else:
                        frame["location_name"] = "Unknown location"
                    frame["latitude"] = pd.to_numeric(frame["latitude"], errors="coerce")
                    frame["longitude"] = pd.to_numeric(frame["longitude"], errors="coerce")
                    frame = frame.dropna(subset=["latitude", "longitude"])
                    frame["women_protest_count"] = women_flag
                    frame["protest_count"] = 1
                    return frame[["latitude", "longitude", "location_name", "women_protest_count", "protest_count"]]

                map_frames = [frame for frame in [build_map_frame(df_women, 1), build_map_frame(df_other, 0)] if frame is not None]
                if map_frames:
                    map_data = pd.concat(map_frames)
                    map_data = (
                        map_data.groupby(["latitude", "longitude", "location_name"], as_index=False)[["women_protest_count", "protest_count"]]
                        .sum()
                    )
                    map_data["radius"] = (
                        map_data["women_protest_count"]
                        .clip(lower=1)
                        .pow(0.35)
                        .mul(1400)
                        .clip(upper=12000)
                    )

            if report_mode == "LLM report":
                with st.spinner(
                    f"Generating analytical text with {llm_provider} ({model_name}) using the {analysis_skill} skill..."
                ):
                    report_result = generate_report_text(
                        selected_country,
                        summary_women,
                        summary_other,
                        provider=llm_provider,
                        analysis_skill=analysis_skill,
                        additional_context=additional_context,
                        women_peak_dates_summary=peak_dates_to_text(women_peak_dates),
                        overall_peak_dates_summary=peak_dates_to_text(overall_peak_dates),
                    )
                report_text = collapse_bullets_to_paragraphs(report_result["text"])
                usage = report_result.get("usage")
            else:
                usage = None
                report_text = build_python_metrics_report({
                    "analysis_skill": analysis_skill,
                    "date_range": date_range,
                    "women_events_count": len(df_women),
                    "other_events_count": len(df_other),
                    "women_peak_dates": women_peak_dates,
                    "overall_peak_dates": overall_peak_dates,
                })
            timestamp_for_file = datetime.now()
            focus_slug = analysis_skill.replace(" ", "_")
            country_slug = selected_country.replace(" ", "_")
            pdf_name = (
                f"Report_{focus_slug}_{country_slug}_"
                f"{timestamp_for_file.strftime('%Y_%m_%d_%H')}.pdf"
            )
            docx_name = (
                f"Report_{focus_slug}_{country_slug}_"
                f"{timestamp_for_file.strftime('%Y_%m_%d_%H')}.docx"
            )

            st.session_state.report_result = {
                "result_schema_version": RESULT_SCHEMA_VERSION,
                "file_signature": file_signature,
                "country": selected_country,
                "date_range": date_range,
                "provider": llm_provider,
                "model_name": model_name,
                "analysis_skill": analysis_skill,
                "report_mode": report_mode,
                "additional_context": additional_context,
                "women_events_count": len(df_women),
                "other_events_count": len(df_other),
                "women_peak_dates": women_peak_dates,
                "overall_peak_dates": overall_peak_dates,
                "timeline_data": timeline_data,
                "timeline_metrics_data": timeline_metrics_data,
                "time_series_metrics": time_series_metrics,
                "actor_w": actor_w,
                "actor_o": actor_o,
                "geo_w": geo_w,
                "geo_o": geo_o,
                "women_word_frequencies": women_word_frequencies,
                "other_word_frequencies": other_word_frequencies,
                "map_available": map_available,
                "map_data": map_data,
                "report_text": report_text,
                "usage": usage,
                "pdf_name": pdf_name,
                "docx_name": docx_name,
                "pdf_bytes": generate_pdf_bytes(selected_country, report_text, date_range=date_range),
            }
            st.session_state.save_message = None
            if usage:
                st.session_state.usage_history.append({
                    "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "country": selected_country,
                    "analysis_skill": analysis_skill,
                    **usage,
                })

        result = st.session_state.report_result
        matches_current_selection = (
            result
            and result.get("result_schema_version") == RESULT_SCHEMA_VERSION
            and result["file_signature"] == file_signature
            and result["country"] == selected_country
            and result["provider"] == llm_provider
            and result["analysis_skill"] == analysis_skill
            and result.get("report_mode") == report_mode
            and result.get("additional_context", "") == additional_context
        )

        if matches_current_selection:
            col1, col2 = st.columns(2)
            col1.metric("Events (Women)", result["women_events_count"])
            col2.metric("Other protests", result["other_events_count"])
            render_report_result(result)
        elif result and result["file_signature"] == file_signature:
            st.info("Generate the analysis again to refresh the saved result for the current visualization settings.")
