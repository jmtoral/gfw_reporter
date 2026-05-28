import os
import time
from openai import OpenAI
import anthropic
from google import genai
from dotenv import load_dotenv
from src.utils import format_event_date

load_dotenv()

MODEL_BY_PROVIDER = {
    "OpenAI": "gpt-4o-mini",
    "Anthropic": "claude-3-haiku-20240307",
    "Gemini": "gemini-2.5-flash",
}

# Estimated pricing in USD per 1M tokens.
# Note: these values were verified on May 22, 2026 against official provider pricing pages and
# are used only for rough monitoring in the app. Providers can change pricing at any time, and
# Gemini pricing in particular can differ between the Gemini Developer API and Vertex AI.
PRICING_BY_MODEL = {
    "gpt-4o-mini": {"input_per_million": 0.15, "output_per_million": 0.60},
    "claude-3-haiku-20240307": {"input_per_million": 0.25, "output_per_million": 1.25},
    "gemini-2.5-flash": {"input_per_million": 0.30, "output_per_million": 2.50},
}


def get_model_name(provider: str) -> str:
    """Return the configured model name for the selected provider."""
    return MODEL_BY_PROVIDER.get(provider, "unknown-model")


def estimate_cost(model_name: str, usage: dict) -> float | None:
    """Estimate cost from a local pricing table when rates are configured."""
    pricing = PRICING_BY_MODEL.get(model_name)
    if not pricing:
        return None

    input_rate = pricing.get("input_per_million")
    output_rate = pricing.get("output_per_million")
    if input_rate is None or output_rate is None:
        return None

    input_tokens = usage.get("input_tokens") or 0
    output_tokens = usage.get("output_tokens") or 0

    return ((input_tokens / 1_000_000) * input_rate) + ((output_tokens / 1_000_000) * output_rate)


def build_usage_summary(provider: str, model_name: str, raw_usage, latency_seconds: float) -> dict:
    """Normalize provider-specific usage metadata."""
    usage = {
        "provider": provider,
        "model_name": model_name,
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "latency_seconds": round(latency_seconds, 2),
        "estimated_cost_usd": None,
    }

    if provider == "OpenAI" and raw_usage is not None:
        usage["input_tokens"] = getattr(raw_usage, "prompt_tokens", None)
        usage["output_tokens"] = getattr(raw_usage, "completion_tokens", None)
        usage["total_tokens"] = getattr(raw_usage, "total_tokens", None)
    elif provider == "Anthropic" and raw_usage is not None:
        usage["input_tokens"] = getattr(raw_usage, "input_tokens", None)
        usage["output_tokens"] = getattr(raw_usage, "output_tokens", None)
        input_tokens = usage["input_tokens"] or 0
        output_tokens = usage["output_tokens"] or 0
        usage["total_tokens"] = input_tokens + output_tokens if (usage["input_tokens"] is not None or usage["output_tokens"] is not None) else None
    elif provider == "Gemini" and raw_usage is not None:
        usage["input_tokens"] = getattr(raw_usage, "prompt_token_count", None)
        usage["output_tokens"] = getattr(raw_usage, "candidates_token_count", None)
        usage["total_tokens"] = getattr(raw_usage, "total_token_count", None)

    usage["estimated_cost_usd"] = estimate_cost(model_name, usage)
    return usage


def build_prompts(
    country: str,
    women_events_summary: str,
    other_protests_summary: str,
    analysis_skill: str = "General",
    additional_context: str = "",
    women_peak_dates_summary: str = "",
    overall_peak_dates_summary: str = "",
):
    """Build system and user prompts for the selected analysis lens."""
    base_system_prompt = (
        "You are an expert data analyst and political scientist. IMPORTANT: "
        "Your response must contain ONLY the requested Markdown report. Do not include any "
        "greetings, introductions, or conversational fillers like 'Here is the report', "
        "'As an analyst', or 'I am a researcher'. Start directly with the title of the first section. "
        "STRICT STYLE RULES: Do NOT use em dashes (—). Do NOT use the word 'vibrant'. Use the absolute minimum number of adjectives possible."
    )

    base_context = f"""
    Draft a professional report on the mobilizations in {country} based strictly on the following ACLED data.

    Context regarding women's mobilizations:
    {women_events_summary}

    Context regarding other relevant protests:
    {other_protests_summary}

    Peak dates for women's mobilizations:
    {women_peak_dates_summary or "No peak dates available."}

    Peak dates for all protests in scope:
    {overall_peak_dates_summary or "No peak dates available."}
    """

    additional_context_block = ""
    if additional_context.strip():
        additional_context_block = f"""

    Additional external context provided by the user (for example, newspaper notes, civil society notes, or contextual observations):
    {additional_context.strip()}
    """

    if analysis_skill == "Women and Gender Focus":
        system_prompt = (
            base_system_prompt
            + " Prioritize gender analysis, women's rights, intersectional risks, civic space, "
            + "and the experiences of women and girls. Use a neutral, analytical tone with few adjectives. "
            + "Avoid rhetorical or overly dramatic phrasing. Avoid unsupported claims."
        )
        prompt = f"""
        {base_context}
        {additional_context_block}

        Use a gender-sensitive and women-centered analytical lens.
        Follow this structure exactly, using Markdown headings and prose paragraphs rather than bullet points:

        ## 1. Protest Dynamics Around Gender and Intersectional Agendas
        Write a narrative analysis of the protest dynamics captured in the ACLED summaries.
        Start with the time period covered by the available events and describe the overall visibility,
        scale, and geography of mobilization. Then explain the most salient protest trends connected to
        women and girls, such as gender-based violence, public safety, institutional accountability,
        health, education, labor, reproductive rights, or political participation, only when supported by the data.
        Explicitly mention the dates with the highest protest activity overall and the dates with the highest women's protest activity when those dates are available, and integrate them into prose paragraphs rather than bullets.
        Compare women's mobilizations against other protests only when it helps explain differences in patterns,
        risks, demands, actors, or state response.
        Include a brief assessment of whether intersectional agendas such as LGBTQI+ rights, Indigenous rights,
        environmental justice, racial justice, disability rights, or other marginalized-group concerns appear visible,
        limited, absent, or underreported in the ACLED event summaries.

        ## 2. Broader Civil Society and Media Trends
        Write this section as an analytical synthesis of likely broader trends connected to the ACLED evidence.
        Ground the section in the event summaries first, then carefully infer what they may suggest about public debate,
        civil society concern, institutional trust, accountability demands, or advocacy patterns.
        If additional external context is provided by the user, use it in this section and make clear when a point comes from that external context rather than from ACLED events.
        If the dataset alone is not sufficient to support a strong claim, explicitly say the evidence is limited.
        Do not invent specific media outlets, reports, organizations, campaigns, or hyperlinks that are not present in the data provided by the user.

        ## 3. Potential Actors Connected to Most Salient Issue/s
        Add a concise Markdown table with exactly these columns:
        | Organization | Focus Area | Geography | Contact |
        Include all organizations, movements, unions, associations, civil society groups, advocacy networks, student groups,
        professional associations, and state-linked actors that are mentioned in the event summaries or can be directly extracted
        from the event notes.
        Prioritize specific named groups over generic categories. For example, prefer a concrete organization name over labels such as
        "protesters", "women", "students", "police", or "community members" whenever a named group is available.
        Order the table so that the most specific and most salient organizations appear first, followed by broader or less specific actors.
        Within that ordering, place rows with usable contact information first, then rows with clear geography, and then the remaining rows.
        Keep one row per organization whenever possible and avoid duplicate or near-duplicate entries.
        If multiple organizations are detected, include all of them rather than a short sample.
        In the Geography column, include the most relevant location, city, district, department, state, or country associated with the actor
        based on the available event summaries. If no geographic association can be inferred from the data, write `Not specified in ACLED data`.
        If contact information is not available in the data, write `Not provided in ACLED data`.

        STRICT RULES:
        - Base every claim on the provided event summaries.
        - Treat the ACLED event summaries as the primary source and the user-provided external context as secondary context.
        - Preserve the three numbered section headings exactly as written above.
        - Whenever March 8th appears in the analysis, explicitly identify it as International Women's Day.
        - If the data is limited, say so briefly inside the relevant section.
        - Use paragraph-style analysis in sections 1 and 2.
        - Keep the writing concise, neutral, and analytical. Use fewer adjectives and avoid advocacy-style wording.
        - Do not include a separate executive summary.
        - In section 3, avoid collapsing distinct organizations into one generic row when the notes mention separate groups.
        - Do not use bullet lists in sections 1 or 2.
        - Omit any text that is not part of the report.
        """
    else:
        system_prompt = base_system_prompt
        prompt = f"""
        {base_context}
        {additional_context_block}

        Please include the following sections in Markdown format:
        1. **Executive Summary**: A general analytical summary.
        2. **Organizations Involved**: Explicitly extract the most active entities (organizations, groups) mentioned.
        3. **Main Themes**: The most relevant topics that motivated the protests.

        STRICT RULES:
        - Treat the ACLED event summaries as the primary source.
        - Mention the dates with the highest protest activity overall and for women's mobilizations when those dates are available, and include them in prose rather than bullets.
        - If additional external context is provided by the user, use it carefully as secondary context and do not invent unsupported claims.
        - Omit any text that is not part of the report (no conversational introductions or conclusions).
        """

    return system_prompt, prompt


def generate_report_text(
    country: str,
    women_events_summary: str,
    other_protests_summary: str,
    provider: str = "OpenAI",
    analysis_skill: str = "General",
    additional_context: str = "",
    women_peak_dates_summary: str = "",
    overall_peak_dates_summary: str = "",
) -> str:
    """Calls the selected LLM provider to generate the report text and extract entities/topics."""
    system_prompt, prompt = build_prompts(
        country,
        women_events_summary,
        other_protests_summary,
        analysis_skill=analysis_skill,
        additional_context=additional_context,
        women_peak_dates_summary=women_peak_dates_summary,
        overall_peak_dates_summary=overall_peak_dates_summary,
    )
    model_name = get_model_name(provider)
    
    try:
        if provider == "OpenAI":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return {"text": "Error: No se encontró OPENAI_API_KEY.", "usage": None}
            client = OpenAI(api_key=api_key)
            started_at = time.perf_counter()
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            usage = build_usage_summary(provider, model_name, getattr(response, "usage", None), time.perf_counter() - started_at)
            return {"text": response.choices[0].message.content, "usage": usage}
            
        elif provider == "Anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                return {"text": "Error: No se encontró ANTHROPIC_API_KEY.", "usage": None}
            client = anthropic.Anthropic(api_key=api_key)
            started_at = time.perf_counter()
            response = client.messages.create(
                model=model_name,
                max_tokens=2048,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            usage = build_usage_summary(provider, model_name, getattr(response, "usage", None), time.perf_counter() - started_at)
            return {"text": response.content[0].text, "usage": usage}
            
        elif provider == "Gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                return {"text": "Error: No se encontró GEMINI_API_KEY.", "usage": None}
            client = genai.Client(api_key=api_key)
            started_at = time.perf_counter()
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.7,
                ),
            )
            usage = build_usage_summary(
                provider,
                model_name,
                getattr(response, "usage_metadata", None),
                time.perf_counter() - started_at,
            )
            return {"text": response.text, "usage": usage}
            
        else:
            return {"text": f"Error: Proveedor {provider} no soportado.", "usage": None}
            
    except Exception as e:
        return {"text": f"Error al generar texto con {provider}: {str(e)}", "usage": None}

def summarize_events_for_llm(df, max_events=30):
    """Convierte un DataFrame de eventos en un string resumido para el contexto del LLM."""
    if df is None or df.empty:
        return "No events found in this category."
    
    df_sample = df.head(max_events)
    
    summary = ""
    for _, row in df_sample.iterrows():
        date = format_event_date(row.get('event_date', 'Unknown date'))
        actor = row.get('actor1', 'Unknown actor')
        notes = row.get('notes', 'No description')
        summary += f"- {date} | {actor}: {notes}\n"
    return summary
