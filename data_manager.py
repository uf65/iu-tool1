import os
import hashlib
import pandas as pd
from typing import List, Dict, Any

CORE_COLUMNS = [
    'Job-ID',
    'Titel',
    'Praxisort',
    'Campus',
    'Studienstart',
    'Über die Stelle',
    'Das bieten wir',
    'Das bringst du mit'
]

def generate_job_id(title: str, location: str, campus: str, start_date: str) -> str:
    """Generate a unique stable Job-ID based on core fields."""
    t = str(title).strip().lower()
    l = str(location).strip().lower()
    c = str(campus).strip().lower()
    s = str(start_date).strip().lower()
    
    unique_str = f"{t}|{l}|{c}|{s}"
    return hashlib.md5(unique_str.encode('utf-8')).hexdigest()[:16]

def load_jobs_csv(filepath: str) -> pd.DataFrame:
    """Loads the jobs CSV if it exists, otherwise returns an empty DataFrame with core columns."""
    if os.path.exists(filepath):
        try:
            df = pd.read_csv(filepath)
            # Ensure core columns exist
            for col in CORE_COLUMNS:
                if col not in df.columns:
                    df[col] = ""
            return df
        except Exception:
            pass
    return pd.DataFrame(columns=CORE_COLUMNS)

def merge_and_save_jobs(scraped_jobs: List[Dict[str, Any]], filepath: str) -> pd.DataFrame:
    """
    Merges scraped jobs with existing jobs in the CSV.
    Preserves user columns and updates core scraped data.
    """
    df_scraped = pd.DataFrame(scraped_jobs)
    if df_scraped.empty:
        df_scraped = pd.DataFrame(columns=CORE_COLUMNS)
    else:
        df_scraped['Job-ID'] = df_scraped.apply(
            lambda r: generate_job_id(r.get('Titel', ''), r.get('Praxisort', ''), r.get('Campus', ''), r.get('Studienstart', '')),
            axis=1
        )
        for col in CORE_COLUMNS:
            if col not in df_scraped.columns:
                df_scraped[col] = ""
        df_scraped = df_scraped[CORE_COLUMNS]

    df_existing = load_jobs_csv(filepath)
    
    if df_existing.empty or len(df_existing) == 0:
        df_merged = df_scraped
    else:
        user_cols = [col for col in df_existing.columns if col not in CORE_COLUMNS]
        
        df_existing_idx = df_existing.set_index('Job-ID')
        df_scraped_idx = df_scraped.set_index('Job-ID')
        
        all_ids = df_existing_idx.index.union(df_scraped_idx.index)
        
        df_merged = pd.DataFrame(index=all_ids)
        df_merged.index.name = 'Job-ID'
        
        for col in CORE_COLUMNS:
            if col == 'Job-ID':
                continue
            scraped_series = df_scraped_idx[col] if col in df_scraped_idx.columns else pd.Series(dtype='object')
            existing_series = df_existing_idx[col] if col in df_existing_idx.columns else pd.Series(dtype='object')
            df_merged[col] = scraped_series.combine_first(existing_series)
            
        for col in user_cols:
            df_merged[col] = df_existing_idx[col]
            df_merged[col] = df_merged[col].fillna("")
            
        df_merged = df_merged.reset_index()
        
        final_cols = CORE_COLUMNS + user_cols
        df_merged = df_merged[final_cols]

    # Use utf-8-sig to display Umlauts correctly in Excel
    df_merged.to_csv(filepath, index=False, encoding='utf-8-sig')
    return df_merged
