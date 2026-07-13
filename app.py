import streamlit as st
import json
import os
import pandas as pd
from data_manager import load_jobs_csv, merge_and_save_jobs
from scraper import scrape_jobs

st.set_page_config(
    page_title="IU Job Scraper Tool",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom premium styling
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap');
html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
    font-family: 'Outfit', sans-serif;
}
.main-title {
    font-size: 2.8rem;
    font-weight: 800;
    background: linear-gradient(90deg, #FF4B4B 0%, #8A2387 50%, #E94057 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0.2rem;
    margin-top: -1rem;
}
.subtitle {
    font-size: 1.1rem;
    color: #888888;
    margin-bottom: 2rem;
}
.metric-card {
    background-color: #1E1E2F;
    border-radius: 12px;
    padding: 1.5rem;
    border: 1px solid #2D2D44;
    box-shadow: 0 4px 15px rgba(0,0,0,0.1);
}
.metric-title {
    font-size: 0.9rem;
    color: #B3B3D4;
    text-transform: uppercase;
    letter-spacing: 1px;
}
.metric-value {
    font-size: 2.2rem;
    font-weight: 600;
    color: #FFFFFF;
    margin-top: 0.2rem;
}
</style>
""", unsafe_allow_html=True)

CONFIG_FILE = "config.json"
CSV_FILE = "jobs.csv"

import os
import pandas as pd
import streamlit as st

CSV_FILE = "iu_jobs.csv"

# --- INITIALISIERUNG BEIM START ---
# Prüfen, ob die CSV-Datei bereits existiert, und in den Session State laden
if "df_jobs" not in st.session_state:
    if os.path.exists(CSV_FILE):
        try:
            st.session_state.df_jobs = pd.read_csv(CSV_FILE)
            # Sicherstellen, dass die Job-ID als String gelesen wird, um Hash-Vergleiche sauber zu halten
            if "Job-ID" in st.session_state.df_jobs.columns:
                st.session_state.df_jobs["Job-ID"] = st.session_state.df_jobs["Job-ID"].astype(str)
        except Exception as e:
            st.warning(f"Bestehende CSV konnte nicht gelesen werden: {e}")
            st.session_state.df_jobs = pd.DataFrame()
    else:
        st.session_state.df_jobs = pd.DataFrame()

# Lokale Referenz für die UI-Berechnung
df_jobs = st.session_state.df_jobs
total_jobs = len(df_jobs)

def load_config():
    # if os.path.exists(CONFIG_FILE):
    #     try:
    #         with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    #             return json.load(f)
    #     except Exception:
    #         pass
    
    return {
        "url": "https://portal.iu.org",
        "selectors": {
            "card": "div.relative.cursor-pointer",
            
            # Der Gewinner-Titel aus dem Labor
            "title": "xpath=//p[contains(@class, 'text-xl') or contains(@class, 'text-2xl')]",
            
            "location": "xpath=.//p[contains(text(), 'Praxisort')]/parent::div/following-sibling::p",
            "campus": "xpath=.//p[contains(text(), 'Campus')]/parent::div/following-sibling::p",
            "start_date": "xpath=.//p[contains(text(), 'Studienstart')]/parent::div/following-sibling::p",
            
            # 1. Über die Stelle: Der Parent-Container selbst beinhaltet den gesuchten Text
            "detail_about": "xpath=//*[contains(., 'Über die Stelle') and not(.//*[contains(., 'Über die Stelle')])]/parent::*",
            
            # 2. Das bieten wir: Labor-Gewinner (Taktik 1)
            "detail_offer": "xpath=//*[contains(., 'Das bieten wir') and not(.//*[contains(., 'Das bieten wir')])]/following-sibling::div[1]",
            
            # 3. Das bringst du mit: Labor-Gewinner (Taktik 1)
            "detail_reqs": "xpath=//*[contains(., 'Das bringst du mit') and not(.//*[contains(., 'Das bringst du mit')])]/following-sibling::div[1]",
            
            "back_button": "text=allen Stellenanzeigen",
            "load_more_button": "button:has-text('Mehr anzeigen')"
        }
    }
            
def save_config(config_data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)

config = load_config()

# Prüfen, ob wir frisch gescrapte Daten im Session-State haben, andernfalls aus CSV laden
if "jobs_preview" in st.session_state:
    df_jobs = st.session_state["jobs_preview"]
else:
    df_jobs = load_jobs_csv(CSV_FILE)
    
# Sidebar - Settings
with st.sidebar:
    st.image("https://www.iu.de/src/images/logos/iu-logo-white.svg", width=100)
    st.markdown("### ⚙️ Konfiguration")
    url = st.text_input("Portal URL", value=config.get("url", "https://portal.iu.org"))
    selectors = config.get("selectors", {})
    
    card = st.text_input("Job-Karte (Card)", value=selectors.get("card", ""))
    title = st.text_input("Titel", value=selectors.get("title", ""))
    location = st.text_input("Praxisort", value=selectors.get("location", ""))
    campus = st.text_input("Campus", value=selectors.get("campus", ""))
    start_date = st.text_input("Studienstart", value=selectors.get("start_date", ""))
    
    with st.expander("Details & Navigation"):
        detail_about = st.text_area("Über die Stelle", value=selectors.get("detail_about", ""))
        detail_offer = st.text_area("Das bieten wir", value=selectors.get("detail_offer", ""))
        detail_reqs = st.text_area("Das bringst du mit", value=selectors.get("detail_reqs", ""))
        back_button = st.text_input("Zurück-Button", value=selectors.get("back_button", ""))
        load_more_button = st.text_input("'Mehr anzeigen'-Button", value=selectors.get("load_more_button", ""))

    if st.button("Speichern", use_container_width=True):
        save_config({
            "url": url,
            "selectors": {
                "card": card, "title": title, "location": location, "campus": campus, "start_date": start_date,
                "detail_about": detail_about, "detail_offer": detail_offer, "detail_reqs": detail_reqs,
                "back_button": back_button, "load_more_button": load_more_button
            }
        })
        st.success("Konfiguration gespeichert!")
        st.rerun()

# Main UI
st.markdown('<div class="main-title">IU Job Scraper Tool</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Automatisiertes Auslesen von Stellenanzeigen aus dem IU-Portal</div>', unsafe_allow_html=True)

col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("### 🚀 Steuerung")
    st.info("""
    **Bedienungsanleitung:**
    1. Klicke unten auf **🔍 Scraping starten**. Ein sichtbares Browserfenster öffnet sich.
    2. Logge dich im geöffneten Browser ein und wechsle zur Liste der Stellenanzeigen.
    3. **Kein weiterer Klick nötig:** Sobald das Tool die Stellenanzeigen auf deinem Bildschirm erkennt, startet das Auslesen vollautomatisch.
    """)
    
    if st.button("🔍 Scraping starten", use_container_width=True):
        current_selectors = {
            "card": card, "title": title, "location": location, "campus": campus, "start_date": start_date,
            "detail_about": detail_about, "detail_offer": detail_offer, "detail_reqs": detail_reqs,
            "back_button": back_button, "load_more_button": load_more_button
        }
        
        with st.status("Initialisiere Browser...", expanded=True) as status_box:
            def log_callback(message, level="info"):
                if level == "error": status_box.write(f"❌ {message}")
                elif level == "warning": status_box.write(f"⚠️ {message}")
                else: status_box.write(f"ℹ️ {message}")
                    
            try:
                scraped_jobs = scrape_jobs(url, current_selectors, log_callback, st.session_state.df_jobs)
                
                if scraped_jobs:
                    log_callback(f"Verarbeite und speichere {len(scraped_jobs)} Stellenanzeigen...", "info")
                    # Speichern und dem globalen df_jobs zuweisen
                    df_jobs = merge_and_save_jobs(scraped_jobs, CSV_FILE)
                    
                    # Im Session-State merken, damit es auch nach Interaktionen erhalten bleibt
                    st.session_state["jobs_preview"] = df_jobs
                    
                    status_box.update(label=f"Scraping erfolgreich! {len(scraped_jobs)} Jobs importiert.", state="complete")
                    st.balloons()
                    # Am Ende des erfolgreichen try-Blocks beim Scraping:
                    st.session_state.df_jobs = pd.read_csv(CSV_FILE)
                    st.rerun()
                else:
                    status_box.update(label="Scraping beendet (keine Daten extrahiert).", state="error")
            except Exception as ex:
                log_callback(f"Unerwarteter Fehler: {ex}", "error")
                status_box.update(label="Scraping fehlgeschlagen.", state="error")
                # st.stop() ENTFERNT – das blockiert die Streamlit-UI dauerhaft!
        
with col2:
    st.markdown("### 📊 Statistiken")
    total_jobs = len(df_jobs)
    user_cols_count = len([c for c in df_jobs.columns if c not in [
        'Job-ID', 'Titel', 'Praxisort', 'Campus', 'Studienstart', 'Über die Stelle', 'Das bieten wir', 'Das bringst du mit'
    ]])
    
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Gesamtanzahl Stellen</div>
        <div class="metric-value">{total_jobs}</div>
    </div>
    <div style="margin-top: 10px;"></div>
    <div class="metric-card">
        <div class="metric-title">Nutzer-Spalten</div>
        <div class="metric-value">{user_cols_count}</div>
    </div>
    """, unsafe_allow_html=True)

st.divider()

st.markdown("### 📂 Daten-Vorschau (CSV)")
if total_jobs > 0:
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1: f_title = st.text_input("Filter nach Titel", "")
    with col_f2: f_loc = st.text_input("Filter nach Praxisort", "")
    with col_f3: f_camp = st.text_input("Filter nach Campus", "")
        
    df_filtered = df_jobs.copy()
    
    # 1. Sicherstellen, dass die Spalte 'Favorit' existiert (falls alte CSVs geladen werden)
    if 'Favorit' not in df_filtered.columns:
        df_filtered['Favorit'] = False
    else:
        # Sicherstellen, dass Python es als Boolean (True/False) liest
        df_filtered['Favorit'] = df_filtered['Favorit'].astype(bool)

    # 2. Filter anwenden
    if f_title: df_filtered = df_filtered[df_filtered['Titel'].str.contains(f_title, case=False, na=False)]
    if f_loc: df_filtered = df_filtered[df_filtered['Praxisort'].str.contains(f_loc, case=False, na=False)]
    if f_camp: df_filtered = df_filtered[df_filtered['Campus'].str.contains(f_camp, case=False, na=False)]

    # Spaltenanordnung optimieren: 'Favorit' als erste Spalte anzeigen
    cols = ['Favorit'] + [col for col in df_filtered.columns if col != 'Favorit']
    df_filtered = df_filtered[cols]

    # 3. Interaktiver Data Editor statt st.dataframe
    edited_df = st.data_editor(
        df_filtered,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Favorit": st.column_config.CheckboxColumn(
                "❤️ Shortlist",
                help="Markiere diesen Job als Favorit",
                default=False,
            )
        },
        # Macht alle anderen Spalten uneditierbar, nur die Checkbox kann geklickt werden
        disabled=[col for col in df_filtered.columns if col != 'Favorit']
    )

    # 4. Änderungen direkt in die Master-Daten (df_jobs) zurückschreiben & CSV aktualisieren
    if not edited_df.equals(df_filtered):
        # Wir gleichen die Änderungen anhand der 'Job-ID' mit dem Original-DataFrame ab
        for idx, row in edited_df.iterrows():
            job_id = row['Job-ID']
            df_jobs.loc[df_jobs['Job-ID'] == job_id, 'Favorit'] = row['Favorit']
        
        # In CSV abspeichern, damit der Zustand beim nächsten App-Start erhalten bleibt
        df_jobs.to_csv(CSV_FILE, index=False, encoding='utf-8-sig')
        st.rerun() # App neu laden, um geänderte Datenbasis zu bestätigen

    # 5. Download-Bereich
    col_d1, col_d2 = st.columns([1, 4])
    with col_d1:
        csv_data = df_jobs.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(label="💾 CSV herunterladen", data=csv_data, file_name="iu_jobs.csv", mime="text/csv", use_container_width=True)
    with col_d2:
        st.caption(f"Gespeichert unter: `{os.path.abspath(CSV_FILE)}`")
else:
    st.info("Noch keine Stellenanzeigen eingelesen.")