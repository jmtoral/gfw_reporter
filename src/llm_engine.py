import os
from openai import OpenAI
import anthropic
from google import genai
from dotenv import load_dotenv

load_dotenv()

MODEL_BY_PROVIDER = {
    "OpenAI": "gpt-4o-mini",
    "Anthropic": "claude-3-haiku-20240307",
    "Gemini": "gemini-2.5-flash",
}


def get_model_name(provider: str) -> str:
    """Return the configured model name for the selected provider."""
    return MODEL_BY_PROVIDER.get(provider, "unknown-model")


def build_prompts(
    country: str,
    women_events_summary: str,
    other_protests_summary: str,
    analysis_skill: str = "General",
):
    """Build system and user prompts for the selected analysis lens."""
    base_system_prompt = (
        "You are an expert data analyst and political scientist. IMPORTANT: "
        "Your response must contain ONLY the requested Markdown report. Do not include any "
        "greetings, introductions, or conversational fillers like 'Here is the report', "
        "'As an analyst', or 'I am a researcher'. Start directly with the title of the first section."
    )

    base_context = f"""
    Draft a professional report on the mobilizations in {country} based strictly on the following ACLED data.

    Context regarding women's mobilizations:
    {women_events_summary}

    Context regarding other relevant protests:
    {other_protests_summary}
    """

    if analysis_skill == "Gender and Women Focus":
        system_prompt = (
            base_system_prompt
            + " Prioritize gender analysis, women's rights, intersectional risks, civic space, "
            + "and the specific experiences of women and girls. Avoid unsupported claims."
        )
        prompt = f"""
        {base_context}

        Use a gender-sensitive and women-centered analytical lens.
        Follow this structure exactly, using Markdown headings and prose paragraphs rather than bullet points:

        ## 1. Protest Dynamics Around Gender and Intersectional Agendas
        Write a narrative analysis of the protest dynamics captured in the ACLED summaries.
        Start with the time period covered by the available events and describe the overall visibility,
        scale, and geography of mobilization. Then explain the most salient protest trends connected to
        women and girls, such as gender-based violence, public safety, institutional accountability,
        health, education, labor, reproductive rights, or political participation, only when supported by the data.
        Compare women's mobilizations against other protests only when it helps explain differences in patterns,
        risks, demands, actors, or state response.
        Include a brief assessment of whether intersectional agendas such as LGBTQI+ rights, Indigenous rights,
        environmental justice, racial justice, disability rights, or other marginalized-group concerns appear visible,
        limited, absent, or underreported in the ACLED event summaries.

        ## 2. Broader Civil Society and Media Trends
        Write this section as an analytical synthesis of likely broader trends connected to the ACLED evidence.
        Ground the section in the event summaries first, then carefully infer what they may suggest about public debate,
        civil society concern, institutional trust, accountability demands, or advocacy patterns.
        If the dataset alone is not sufficient to support a strong claim, explicitly say the evidence is limited.
        Do not invent specific media outlets, reports, organizations, campaigns, or hyperlinks that are not present in the data provided.

        ## 3. Potential Actors Connected to Most Salient Issue/s
        Add a concise Markdown table with exactly these columns:
        | Organization | Focus Area | Contact |
        Include organizations, movements, unions, associations, civil society groups, or state-linked actors only if they are mentioned
        in the ACLED summaries or can be directly extracted from the event notes. If contact information is not available in the data,
        write `Not provided in ACLED data`.

        STRICT RULES:
        - Base every claim on the provided event summaries.
        - Preserve the three numbered section headings exactly as written above.
        - If the data is limited, say so briefly inside the relevant section.
        - Use paragraph-style analysis in sections 1 and 2.
        - Do not include a separate executive summary.
        - Omit any text that is not part of the report.
        """
    else:
        system_prompt = base_system_prompt
        prompt = f"""
        {base_context}

        Please include the following sections in Markdown format:
        1. **Executive Summary**: A general analytical summary.
        2. **Organizations Involved**: Explicitly extract the most active entities (organizations, groups) mentioned.
        3. **Main Themes**: The most relevant topics that motivated the protests.

        STRICT RULE: Omit any text that is not part of the report (no conversational introductions or conclusions).
        """

    return system_prompt, prompt


def generate_report_text(
    country: str,
    women_events_summary: str,
    other_protests_summary: str,
    provider: str = "OpenAI",
    analysis_skill: str = "General",
) -> str:
    """Calls the selected LLM provider to generate the report text and extract entities/topics."""
    system_prompt, prompt = build_prompts(
        country,
        women_events_summary,
        other_protests_summary,
        analysis_skill=analysis_skill,
    )
    
    try:
        if provider == "OpenAI":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return "Error: No se encontró OPENAI_API_KEY."
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=get_model_name(provider),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            return response.choices[0].message.content
            
        elif provider == "Anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                return "Error: No se encontró ANTHROPIC_API_KEY."
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=get_model_name(provider),
                max_tokens=2048,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return response.content[0].text
            
        elif provider == "Gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                return "Error: No se encontró GEMINI_API_KEY."
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=get_model_name(provider),
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.7,
                ),
            )
            return response.text
            
        else:
            return f"Error: Proveedor {provider} no soportado."
            
    except Exception as e:
        return f"Error al generar texto con {provider}: {str(e)}"

def summarize_events_for_llm(df, max_events=30):
    """Convierte un DataFrame de eventos en un string resumido para el contexto del LLM."""
    if df is None or df.empty:
        return "No events found in this category."
    
    df_sample = df.head(max_events)
    
    summary = ""
    for _, row in df_sample.iterrows():
        date = row.get('event_date', 'Unknown date')
        actor = row.get('actor1', 'Unknown actor')
        notes = row.get('notes', 'No description')
        summary += f"- {date} | {actor}: {notes}\n"
    return summary
