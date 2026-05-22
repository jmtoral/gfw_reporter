import streamlit as st
import pandas as pd
import os
import hashlib
from collections import Counter
from dotenv import load_dotenv

from src.data_processor import get_available_countries, filter_by_country, get_women_mobilizations, get_other_relevant_protests
from src.llm_engine import summarize_events_for_llm, generate_report_text, get_model_name
from src.pdf_generator import generate_pdf_bytes
from src.report_storage import save_report_bundle

load_dotenv()

if "report_result" not in st.session_state:
    st.session_state.report_result = None

if "save_message" not in st.session_state:
    st.session_state.save_message = None


def render_report_result(result):
    st.write("---")
    st.subheader("📊 Data Visualization")

    st.markdown("#### Temporal Evolution")
    if result["timeline_data"] is not None:
        st.line_chart(result["timeline_data"], color=["#d228f4", "#411342"])
    else:
        st.warning("Could not generate timeline due to date format issues.")

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
        st.pydeck_chart(pdk.Deck(
            map_style='light',
            initial_view_state=pdk.ViewState(
                latitude=result["map_data"]['latitude'].mean(),
                longitude=result["map_data"]['longitude'].mean(),
                zoom=6.5,
                pitch=0,
            ),
            layers=[
                pdk.Layer(
                    'ScatterplotLayer',
                    data=result["map_data"],
                    get_position='[longitude, latitude]',
                    get_color='[210, 40, 244, 220]',
                    get_radius=3000,
                ),
            ],
        ))
    elif result["map_available"]:
        st.warning("No coordinate data available for selected filters.")
    else:
        st.warning("Coordinates not found in the file.")

    st.write("---")
    st.subheader("Report Draft")
    st.markdown(result["report_text"])

    st.download_button(
        label="📄 Download PDF Report",
        data=result["pdf_bytes"],
        file_name=result["pdf_name"],
        mime="application/pdf",
    )

    if st.button("Save Results Locally"):
        saved_path = save_report_bundle(result)
        st.session_state.save_message = f"Saved report bundle to `{saved_path}`."

    if st.session_state.save_message:
        st.success(st.session_state.save_message)

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

llm_provider = st.sidebar.selectbox("Select AI Provider", ["OpenAI", "Anthropic", "Gemini"])
model_name = get_model_name(llm_provider)
st.sidebar.caption(f"Model in use: `{model_name}`")

analysis_skill = st.sidebar.selectbox(
    "Analysis skill",
    ["General", "Gender and Women Focus"],
    help="Choose the analytical lens used to draft the report.",
)

if analysis_skill == "Gender and Women Focus":
    st.sidebar.info(
        "This skill prioritizes women-led mobilizations, gender dynamics, risks, "
        "rights claims, and protection concerns grounded in the ACLED notes."
    )

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

st.title("ACLED Report Generator")
st.markdown("Upload an ACLED CSV file to filter data, generate AI analysis, and download the PDF report.")
st.caption(f"Current model: `{model_name}` | Current analysis skill: `{analysis_skill}`")

# File uploader
uploaded_file = st.file_uploader("Upload ACLED CSV file", type=["csv"])

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
        if st.button("Generate Analysis and Report"):
            # Check for API Key
            if not os.getenv(f"{llm_provider.upper()}_API_KEY"):
                st.error(f"⚠️ Please enter your {llm_provider} API Key in the left sidebar before continuing.")
                st.stop()
                
            with st.spinner("Filtering data..."):
                df_country = filter_by_country(df, selected_country)
                
                # Women mobilizations
                df_women = get_women_mobilizations(df_country)
                
                # Other protests
                df_other = get_other_relevant_protests(df_country, exclude_indices=df_women.index)
                
                col1, col2 = st.columns(2)
                col1.metric("Events (Women)", len(df_women))
                col2.metric("Other protests", len(df_other))
                
                summary_women = summarize_events_for_llm(df_women)
                summary_other = summarize_events_for_llm(df_other)

                timeline_data = None
            try:
                df_w_time = df_women.copy()
                df_w_time['Fecha'] = pd.to_datetime(df_w_time['event_date'], errors='coerce')
                ts_w = df_w_time.dropna(subset=['Fecha']).groupby(df_w_time['Fecha'].dt.to_period('M').dt.start_time).size().rename("Women's Mobilizations")
                
                df_o_time = df_other.copy()
                df_o_time['Fecha'] = pd.to_datetime(df_o_time['event_date'], errors='coerce')
                ts_o = df_o_time.dropna(subset=['Fecha']).groupby(df_o_time['Fecha'].dt.to_period('M').dt.start_time).size().rename("Other Protests")
                
                timeline_data = pd.concat([ts_w, ts_o], axis=1).fillna(0)
            except Exception as e:
                timeline_data = None

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

            map_available = 'latitude' in df.columns and 'longitude' in df.columns
            map_data = None
            if map_available:
                map_data = pd.concat([df_women[['latitude', 'longitude']], df_other[['latitude', 'longitude']]]).dropna()

            with st.spinner(
                f"Generating analytical text with {llm_provider} ({model_name}) using the {analysis_skill} skill..."
            ):
                report_text = generate_report_text(
                    selected_country,
                    summary_women,
                    summary_other,
                    provider=llm_provider,
                    analysis_skill=analysis_skill,
                )

            st.session_state.report_result = {
                "file_signature": file_signature,
                "country": selected_country,
                "provider": llm_provider,
                "model_name": model_name,
                "analysis_skill": analysis_skill,
                "women_events_count": len(df_women),
                "other_events_count": len(df_other),
                "timeline_data": timeline_data,
                "actor_w": actor_w,
                "actor_o": actor_o,
                "geo_w": geo_w,
                "geo_o": geo_o,
                "map_available": map_available,
                "map_data": map_data,
                "report_text": report_text,
                "pdf_name": f"Report_{selected_country.replace(' ', '_')}.pdf",
                "pdf_bytes": generate_pdf_bytes(selected_country, report_text),
            }
            st.session_state.save_message = None

        result = st.session_state.report_result
        matches_current_selection = (
            result
            and result["file_signature"] == file_signature
            and result["country"] == selected_country
            and result["provider"] == llm_provider
            and result["analysis_skill"] == analysis_skill
        )

        if matches_current_selection:
            col1, col2 = st.columns(2)
            col1.metric("Events (Women)", result["women_events_count"])
            col2.metric("Other protests", result["other_events_count"])
            render_report_result(result)
        elif result and result["file_signature"] == file_signature:
            st.info("Generate the analysis again to refresh the saved result for the current provider or skill.")
