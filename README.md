# Event Source Reporter

Event Source Reporter is a Streamlit app for exploring structured event datasets and turning them into fast analytical briefs with LLM support.

The current implementation is optimized for ACLED-like CSV files, especially sources that include fields such as `country`, `event_date`, `event_type`, `actor1`, `actor2`, `notes`, `location`, `admin1`, `admin2`, `latitude`, and `longitude`. The project is intentionally modular so the ingestion and analysis logic can be adapted to other event-based sources.

## What it does

- Filters events by country.
- Separates women- and gender-related mobilizations from other protests.
- Generates visual summaries for time trends, top actors, top geographies, and map distribution.
- Produces an LLM-written analytical report using OpenAI, Anthropic, or Gemini.
- Supports a dedicated `Women and Gender Focus` analysis skill with a fixed report structure.
- Accepts optional free-text contextual notes, such as newspaper excerpts or NGO summaries, before report generation.
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

### Conda alternative

If you prefer Conda, you can create and use an environment like this:

```bash
conda create -n gfw_reporter python=3.12
conda activate gfw_reporter
pip install -r requirements.txt
```

If your team standardizes on Conda, this is a good default because it makes onboarding easier across machines.

## Run on another computer

To use this project on someone else's computer:

1. Install Python 3.11 or 3.12.
2. Clone the repository:

```bash
git clone https://github.com/jmtoral/gfw_reporter.git
cd gfw_reporter
```

3. Create and activate a virtual environment.

On Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

On macOS or Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

4. Install dependencies:

```bash
pip install -r requirements.txt
```

5. Either:

- export an API key as an environment variable, or
- paste the provider key directly into the sidebar once the app is running

6. Start the app:

```bash
streamlit run app.py
```

7. Open the local URL shown by Streamlit, usually:

```text
http://localhost:8501
```

### Run on another computer with Conda

If the other person uses Conda, they can also do:

```bash
git clone https://github.com/jmtoral/gfw_reporter.git
cd gfw_reporter
conda create -n gfw_reporter python=3.12
conda activate gfw_reporter
pip install -r requirements.txt
streamlit run app.py
```

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

## Typical workflow

1. Upload a structured source CSV.
2. Select a country.
3. Optionally paste additional context such as newspaper notes, NGO summaries, or field observations.
4. Choose the provider and analysis skill.
5. Generate the report.
6. Download the PDF or save the report bundle locally.

## Additional context notes

The app includes an optional free-text field called `Additional context for the report`.

Use it for:

- newspaper excerpts
- NGO summaries
- field observations
- contextual notes from researchers
- short media digests

Recommended guidance:

- paste plain text instead of raw HTML
- include source names in the text if they matter
- separate different notes with blank lines
- keep the text focused on the selected country and time period
- prefer concise excerpts or summaries over extremely long dumps
- short curated excerpts usually work better than copying entire articles
- if you paste quoted language, keep only the parts that are analytically relevant

Current behavior:

- the app does not require a strict template for these notes
- the notes are treated as secondary context, while the uploaded event CSV remains the primary source
- the model is instructed not to invent sources beyond what the user pasted

Practical limitations:

- there is no hard schema, but very long notes will increase token usage and cost
- if the notes mix multiple countries or time periods, the report may become less precise
- URLs alone are not enough context unless the user also pastes the relevant text or summary
- if the notes contain conflicting claims, the model may reflect that ambiguity rather than resolve it
- the app does not currently validate source quality, so users should curate notes before pasting them

## How to adapt this to other sources

To generalize the reporter beyond ACLED-like data, the usual path is:

1. Replace or extend the filtering logic in `src/data_processor.py`.
2. Adjust the prompt context builder in `src/llm_engine.py`.
3. Update chart field mappings in `app.py`.
4. Add source-specific validation rules before report generation.

## Notes

- The app currently generates analysis from the uploaded dataset only.
- Broader media or civil society context is not fetched automatically from the internet.
- The `Women and Gender Focus` skill is designed to stay grounded in the uploaded event summaries and avoid unsupported claims.
