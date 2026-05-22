import pandas as pd

def get_available_countries(df: pd.DataFrame) -> list:
    """Returns a sorted list of unique countries in the dataframe."""
    if 'country' in df.columns:
        return sorted(df['country'].dropna().unique().tolist())
    return []

def filter_by_country(df: pd.DataFrame, country: str) -> pd.DataFrame:
    """Filters the dataset by country."""
    if country and 'country' in df.columns:
        return df[df['country'].str.contains(country, case=False, na=False)]
    return df

def get_women_mobilizations(df: pd.DataFrame) -> pd.DataFrame:
    """Filters events related to women and gender issues."""
    keywords = [
        "woman", "women", "female", "girl", "girls",
        "gender", "feminism", "feminist",
        "pregnancy", "abortion",
        "rape", "sexual violence", "domestic violence",
        "gender-based violence", "gbv",
        "femicide", "women's rights", "mujeres", "mujer", "niñas", "feminista"
    ]
    pattern = '|'.join(keywords)
    
    mask_notes = pd.Series(False, index=df.index)
    if 'notes' in df.columns:
        mask_notes = df['notes'].str.contains(pattern, case=False, na=False)
    
    mask_actors = pd.Series(False, index=df.index)
    actor_cols = ['actor1', 'assoc_actor_1', 'actor2', 'assoc_actor_2']
    for col in actor_cols:
        if col in df.columns:
            mask_actors = mask_actors | df[col].str.contains(pattern, case=False, na=False)
            
    return df[mask_notes | mask_actors]

def get_other_relevant_protests(df: pd.DataFrame, exclude_indices=None) -> pd.DataFrame:
    """Gets other protests/mobilizations."""
    protest_types = ['Protests', 'Riots']
    
    if 'event_type' in df.columns:
        mask_protests = df['event_type'].isin(protest_types)
        df_protests = df[mask_protests]
    else:
        df_protests = df.copy()
        
    if exclude_indices is not None and not df_protests.empty:
        df_protests = df_protests.drop(index=exclude_indices, errors='ignore')
        
    return df_protests
