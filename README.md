# Event Source Reporter

Event Source Reporter is a Streamlit app for exploring structured event datasets and turning them into fast analytical briefs with LLM support.

The current implementation is optimized for ACLED-like CSV files, especially sources that include fields such as `country`, `event_date`, `event_type`, `actor1`, `actor2`, `notes`, `location`, `admin1`, `admin2`, `latitude`, and `longitude`. The project is intentionally modular so the ingestion and analysis logic can be adapted to other event-based sources.

## What it does

- Filters events by country.
- Separates women- and gender-related mobilizations from other protests.
- Generates visual summaries for time trends, top actors, top geographies, and map distribution.
- Produces an LLM-written analytical report using OpenAI, Anthropic, or Gemini.
- Supports a dedicated `Gender and Women Focus` analysis skill with a fixed report structure.
- Exports the result to PDF.
- Keeps the latest result visible in the app after download.
- Allows saving report bundles locally as Markdown, PDF, and metadata.

## Current scope

This repository is not a fully generic ingestion engine yet.

Today, the app assumes:

- A CSV input file.
- A country column for geographic filtering.
- ACLED-style event and actor fields.
- Text notes that can be summarized for the model.

If you want to adapt it to another source, the main places to extend are:

- `app.py` for UI and workflow.
- `src/data_processor.py` for source-specific filtering logic.
- `src/llm_engine.py` for prompt design and provider/model behavior.
- `src/pdf_generator.py` for export formatting.

## Repository structure

```text
.
├── app.py
├── requirements.txt
├── .streamlit/
└── src/
    ├── data_processor.py
    ├── llm_engine.py
    ├── pdf_generator.py
    └── report_storage.py
```

## Setup

1. Create or activate a Python environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set one or more provider keys as environment variables:

```bash
OPENAI_API_KEY=your_key
ANTHROPIC_API_KEY=your_key
GEMINI_API_KEY=your_key
```

You can also paste the selected provider key directly in the Streamlit sidebar at runtime.

## Run the app

```bash
streamlit run app.py
```

## Recommended input schema

The best experience currently comes from a dataset with columns like:

```text
country
event_date
event_type
actor1
assoc_actor_1
actor2
assoc_actor_2
notes
location
admin1
admin2
latitude
longitude
```

## How to adapt this to other sources

To generalize the reporter beyond ACLED-like data, the usual path is:

1. Replace or extend the filtering logic in `src/data_processor.py`.
2. Adjust the prompt context builder in `src/llm_engine.py`.
3. Update chart field mappings in `app.py`.
4. Add source-specific validation rules before report generation.

## Notes

- The app currently generates analysis from the uploaded dataset only.
- Broader media or civil society context is not fetched automatically from the internet.
- The `Gender and Women Focus` skill is designed to stay grounded in the uploaded event summaries and avoid unsupported claims.
