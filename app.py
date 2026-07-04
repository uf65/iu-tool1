import streamlit as st
import json
import os
import pandas as pd
from data_manager import load_jobs_csv, merge_and_save_jobs
from scraper import init_browser, extract_jobs_from_page

st.set_page_config(
    page_title="IU Job Scraper Tool",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="collapsed"
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

if "scraper_context" not in st.session_state:
    st.session_state.scraper_context = None
if "step" not in st.session_state:
    st.session_state.step = "ready"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # Präzise auf das HTML-Bildschirmfoto abgestimmte Selektoren
    return {
        "url": "https://portal.iu.org",
        "selectors": {
            "card": "css=div.relative.cursor-pointer",
            "title": "css=p.text-xl",
            "location": "xpath=.//p[contains(text(), 'Praxisort')]/parent::div/following-sibling::p",
            "campus": "xpath=.//p[contains(text(), 'Campus')]/parent::div/following-sibling::p",
            "start_date": "xpath=.//p[contains(text(), 'Studienstart')]/parent::div/following-sibling::p",
            "detail_about": "xpath=//h3[contains(text(), 'Über die Stelle')]/following-sibling::div[1] | xpath=//div[contains(., 'Über die Stelle')]/following-sibling::div[1]",
            "detail_offer": "xpath=//h3[contains(text(), 'Das bieten wir')]/following-sibling::div[1] | xpath=//div[contains(., 'Das bieten wir')]/following-sibling::div[1]",
            "detail_reqs": "xpath=//h3[contains(text(), 'Das bringst du mit')]/following-sibling::div[1] | xpath=//div[contains(., 'Das bringst du mit')]/following-sibling::div[1]",
            "back_button": "text=zurück zu den Stellenanzeigen",
            "load_more_button": "text=mehr anzeigen"
        }
    }

config = load_config()
df_jobs = load_jobs_csv(CSV_FILE)

st.markdown('<div class="main-title">IU Job Scraper Tool</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Automatisiertes Auslesen von Stellenanzeigen aus dem IU-Portal</div>', unsafe_allow_html=True)

col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("### 🚀 Steuerung")
    
    if st.session_state.step == "ready":
        st.info("""
        **Nächster Schritt:** Klicke auf **Browser öffnen**, logge dich im neuen Fenster ein und gehe zur Jobliste.
        """)
        if st.button("🌐 1. Browser öffnen & Navigieren", use_container_width=True):
            with st.status("Starte Browser-Instanz...", expanded=True) as status:
                try:
                    ctx = init_browser(config.get("url", "https://portal.iu.org"))
                    st.session_state.scraper_context = ctx
                    st.session_state.step = "waiting_for_login"
                    status.update(label="Browser erfolgreich geöffnet! Bitte logge dich ein.", state="complete")
                    st.rerun()
                except Exception as e:
                    status.update(label=f"Fehler beim Starten des Browsers: {e}", state="error")

    elif st.session_state.step == "waiting_for_login":
        st.warning("""
        **Aktion erforderlich:** Bitte logge dich jetzt im geöffneten Browser-Fenster ein und navigiere zur Liste der Stellenanzeigen.
        """)
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("✅ 2. Login erfolgreich – Scraping jetzt starten", type="primary", use_container_width=True):
                st.session_state.step = "scraping"
                st.rerun()
        with col_btn2:
            if st.button("❌ Abbrechen", use_container_width=True):
                if st.session_state.scraper_context:
                    try:
                        st.session_state.scraper_context["browser"].close()
                        st.session_state.scraper_context["playwright"].stop()
                    except: pass
                st.session_state.scraper_context = None
                st.session_state.step = "ready"
                st.rerun()

    elif st.session_state.step == "scraping":
        with st.status("Prüfe Webseiten-Struktur und starte Datenextraktion...", expanded=True) as status_box:
            def log_callback(message, level="info"):
                if level == "error": status_box.write(f"❌ {message}")
                elif level == "warning": status_box.write(f"⚠️ {message}")
                else: status_box.write(f"ℹ️ {message}")
            
            try:
                ctx = st.session_state.scraper_context
                selectors = config.get("selectors", {})
                
                if not ctx:
                    raise Exception("Browser-Kontext verloren gegangen. Bitte von vorn beginnen.")
                
                scraped_jobs = extract_jobs_from_page(ctx["page"], ctx["context"], selectors, log_callback)
                
                if scraped_jobs:
                    log_callback(f"Speichere {len(scraped_jobs)} Stellenanzeigen in `{CSV_FILE}`...", "info")
                    df_jobs = merge_and_save_jobs(scraped_jobs, CSV_FILE)
                    status_box.update(label=f"Scraping erfolgreich! {len(scraped_jobs)} Jobs ausgelesen.", state="complete")
                    st.balloons()
                else:
                    status_box.update(label="Scraping beendet. Keine Daten extrahiert.", state="error")
                    
            except Exception as ex:
                log_callback(f"Fehler während des Scrapings: {ex}", "error")
                status_box.update(label="Scraping fehlgeschlagen.", state="error")
            finally:
                if st.session_state.scraper_context:
                    try:
                        st.session_state.scraper_context["browser"].close()
                        st.session_state.scraper_context["playwright"].stop()
                    except: pass
                st.session_state.scraper_context = None
                st.session_state.step = "ready"

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
    if f_title: df_filtered = df_filtered[df_filtered['Titel'].str.contains(f_title, case=False, na=False)]
    if f_loc: df_filtered = df_filtered[df_filtered['Praxisort'].str.contains(f_loc, case=False, na=False)]
    if f_camp: df_filtered = df_filtered[df_filtered['Campus'].str.contains(f_camp, case=False, na=False)]

    st.dataframe(df_filtered, use_container_width=True)
    
    col_d1, col_d2 = st.columns([1, 4])
    with col_d1:
        csv_data = df_jobs.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(label="💾 CSV herunterladen", data=csv_data, file_name="iu_jobs.csv", mime="text/csv", use_container_width=True)
    with col_d2:
        st.caption(f"Gespeichert unter: `{os.path.abspath(CSV_FILE)}`")
else:
    st.info("Noch keine Stellenanzeigen eingelesen.")