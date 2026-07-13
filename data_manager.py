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
    Preserves user columns and updates core scraped data without index conflicts.
    """
    # 1. Scraped Data in DataFrame umwandeln
    df_scraped = pd.DataFrame(scraped_jobs)
    if df_scraped.empty:
        df_scraped = pd.DataFrame(columns=CORE_COLUMNS)
    else:
        # Falls die Job-ID nicht schon im Scraper generiert wurde, hier berechnen
        if 'Job-ID' not in df_scraped.columns:
            df_scraped['Job-ID'] = df_scraped.apply(
                lambda r: generate_job_id(r.get('Titel', ''), r.get('Praxisort', ''), r.get('Campus', ''), r.get('Studienstart', '')),
                axis=1
            )
        # Core-Spalten sicherstellen
        for col in CORE_COLUMNS:
            if col not in df_scraped.columns:
                df_scraped[col] = ""
        df_scraped = df_scraped[CORE_COLUMNS]

    # 2. Bestehende Daten laden
    df_existing = load_jobs_csv(filepath)
    
    # Wenn noch keine alten Daten da sind, sind die neuen Daten das Endergebnis
    if df_existing.empty or len(df_existing) == 0:
        df_merged = df_scraped
    else:
        # Dynamisch alle Spalten ermitteln, die vom Nutzer stammen (z.B. 'Favorit')
        user_cols = [col for col in df_existing.columns if col not in CORE_COLUMNS]
        
        # --- SCHRITT A: Core-Daten zusammenführen ---
        # Wir kleben alt und neu einfach untereinander (ignore_index bereinigt die Zeilennummern!)
        df_core_combined = pd.concat([df_existing[CORE_COLUMNS], df_scraped], ignore_index=True)
        
        # Duplikate auf Spalten-Ebene löschen. 'keep=last' sorgt dafür, 
        # dass die frisch gescrapten Daten die alten Werte überschreiben.
        df_core_merged = df_core_combined.drop_duplicates(subset=['Job-ID'], keep='last')
        
        # --- SCHRITT B: User-Spalten (z.B. Favoriten-Zustand) retten ---
        if user_cols:
            # Wir isolieren die User-Spalten aus den Alt-Daten anhand der Job-ID
            # Falls im Alt-Bestand Duplikate waren, reinigen wir diese hier vorab
            df_user_data = df_existing[['Job-ID'] + user_cols].drop_duplicates(subset=['Job-ID'], keep='last')
            
            # Per Links-Join (Merge) heften wir die User-Spalten wieder an unsere sauberen Core-Daten an
            df_merged = pd.merge(df_core_merged, df_user_data, on='Job-ID', how='left')
            df_merged[user_cols] = df_merged[user_cols].fillna("")
        else:
            df_merged = df_core_merged
        
        # Spaltenreihenfolge wie gewohnt wiederherstellen
        final_cols = CORE_COLUMNS + user_cols
        df_merged = df_merged[final_cols]

    # Mit BOM speichern für korrekte Umlaut-Anzeige in Excel
    df_merged.to_csv(filepath, index=False, encoding='utf-8-sig')
    return df_merged