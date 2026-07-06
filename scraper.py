import time
from typing import List, Dict, Any, Callable
import playwright
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

import os
import subprocess
import sys

# Prüfen, ob wir in der Streamlit Cloud sind und ob die Browser fehlen
def ensure_playwright_browsers():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return

    # Pfad zum Playwright-Cache prüfen
    if os.environ.get("STREAMLIT_SERVER_SHARING_TEXT_ALLOWED") or not os.path.exists(os.path.expanduser("~/.cache/ms-playwright")):
        try:
            print("⏳ Installiere Playwright Chromium-Browser...")
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
            print("✅ Playwright Browser erfolgreich installiert!")
        except Exception as e:
            print(f"⚠️ Fehler bei der Browser-Installation: {e}")
            
ensure_playwright_browsers()
            
            
def get_text_safe(locator_parent, selector: str) -> str:
    """Safely retrieves inner text from a selector relative to a parent locator."""
    try:
        element = locator_parent.locator(selector).first
        if element.is_visible(timeout=1000):
            return element.inner_text().strip()
    except Exception:
        pass
    return ""

def expand_job_list(page, selectors, status_callback: Callable[[str, str], None]) -> int:
    """Clicks the 'mehr anzeigen' button repeatedly to load all job postings."""
    card_selector = selectors['card']
    load_more_selector = selectors['load_more_button']
    
    last_card_count = page.locator(card_selector).count()
    status_callback(f"Bisher {last_card_count} Stellenanzeigen geladen. Suche nach 'mehr anzeigen'...", "info")
    
    no_change_count = 0
    while True:
        try:
            load_more_btn = page.locator(load_more_selector).first
            if load_more_btn.is_visible(timeout=2000):
                load_more_btn.click(force=True)
                page.wait_for_timeout(2000)
                
                current_card_count = page.locator(card_selector).count()
                if current_card_count > last_card_count:
                    last_card_count = current_card_count
                    no_change_count = 0
                else:
                    no_change_count += 1
                    if no_change_count >= 3:
                        break
            else:
                break
        except Exception:
            break
            
    return page.locator(card_selector).count()

def scrape_jobs(url: str, selectors: Dict[str, str], status_callback: Callable[[str, str], None], iu_email: str, iu_password: str) -> List[Dict[str, Any]]:
    scraped_data = []
    
    with sync_playwright() as p:
        status_callback("Starte unsichtbaren Browser (Headless)...", "info")
        browser = p.chromium.launch(
            headless=True,  # 🚀 Ab jetzt dauerhaft unsichtbar!
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process"
            ]
        )
        
        # Identifiziere dich als normaler Chrome-Browser, um Bot-Sperren zu vermeiden
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900}
        )
        page = context.new_page()
        page.set_default_timeout(30000) # 30 Sekunden Timeout für Aktionen
        
        try:
            status_callback(f"Navigiere zum Portal und lade Login-Maske...", "info")
            page.goto(url)
            
            # --- AUTOMATISCHER LOGIN ---
            status_callback("🤖 Gebe Zugangsdaten automatisch ein...", "info")
            
            # 1. E-Mail eingeben (Sucht nach den typischen Auth0 oder Microsoft Feldern)
            email_locator = page.locator('input[type="email"], input[name="loginfmt"], input[name="username"]').first
            email_locator.wait_for(state="visible")
            email_locator.fill(iu_email)
            page.keyboard.press("Enter")
            
            # Kurze Pause, da Enterprise-Logins oft eine sanfte Überblendung haben
            page.wait_for_timeout(2000)
            
            # 2. Passwort eingeben
            pass_locator = page.locator('input[type="password"], input[name="passwd"]').first
            pass_locator.wait_for(state="visible")
            pass_locator.fill(iu_password)
            page.keyboard.press("Enter")
            
            # 3. Optional: "Angemeldet bleiben?" (Microsoft spezifisch) abfangen
            try:
                stay_signed_in = page.locator('input[type="submit"][value="Ja"], input[type="submit"][id="idSIButton9"]').first
                if stay_signed_in.is_visible(timeout=3000):
                    stay_signed_in.click()
            except Exception:
                pass # Wenn die Abfrage nicht kommt, einfach weitermachen
                
            status_callback("Warte auf Authentifizierung und Weiterleitung zum Portal...", "info")
            
            # --- ERFOLGSPRÜFUNG ---
            # Wir warten darauf, dass die URL auf /selfmatching wechselt ODER der Text Praxisort auftaucht
            page.wait_for_function("window.location.href.includes('/selfmatching') || document.body.innerText.includes('Praxisort')", timeout=20000)
            
            card_count = page.locator(selectors['card']).count()
            if card_count == 0:
                card_count = page.locator("p:has-text('Praxisort')").count()
                
            status_callback(f"🎉 Auto-Login erfolgreich! {card_count} Stellenanzeigen identifiziert.", "complete")
            
        except Exception as e:
            status_callback(f"Login fehlgeschlagen. Möglicherweise falsche Daten, 2FA-Abfrage oder Bot-Schutz aktiv. Fehler: {e}", "error")
            browser.close()
            return []
                        
        # 2. Liste vollständig expandieren
        page.wait_for_timeout(2000)
        total_cards = expand_job_list(page, selectors, status_callback)
        status_callback(f"Insgesamt {total_cards} Stellenanzeigen geladen. Starte Detail-Scraping...", "info")
        
        # 3. Iteration durch die Karten
        i = 0
        while i < total_cards:
            if page.is_closed():
                status_callback("Browser wurde geschlossen während des Scrapings.", "error")
                break
                
            status_callback(f"Scrape Job {i + 1} von {total_cards}...", "info")
            
            try:
                cards = page.locator(selectors['card'])
                current_count = cards.count()
                
                if current_count <= i:
                    status_callback(f"Liste wurde zurückgesetzt. Re-expandiere auf mindestens {i+1}...", "warning")
                    expand_job_list(page, selectors, status_callback)
                    cards = page.locator(selectors['card'])
                    current_count = cards.count()
                    if current_count <= i:
                        i += 1
                        continue
                
                card = cards.nth(i)
                card.scroll_into_view_if_needed()
                
                title = get_text_safe(card, selectors['title'])
                location = get_text_safe(card, selectors['location'])
                campus = get_text_safe(card, selectors['campus'])
                start_date = get_text_safe(card, selectors['start_date'])
                
                status_callback(f"Stelle gefunden: '{title}' in {location} ({campus})", "info")
                
                about, offer, reqs = "", "", ""
                try:
                    with context.expect_page(timeout=2500) as new_page_info:
                        card.click()
                    
                    new_page = new_page_info.value
                    new_page.wait_for_load_state()
                    
                    about = get_text_safe(new_page, selectors['detail_about'])
                    offer = get_text_safe(new_page, selectors['detail_offer'])
                    reqs = get_text_safe(new_page, selectors['detail_reqs'])
                    
                    new_page.close()

                except PlaywrightTimeoutError:
                    # It navigated in the same tab or did an in-place update
                    # Wait for detail content to load on current page
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(1000) # extra safety buffer
                    
                    # Extract detail info
                    about = get_text_safe(page, selectors['detail_about'])
                    offer = get_text_safe(page, selectors['detail_offer'])
                    reqs = get_text_safe(page, selectors['detail_reqs'])
                    status_callback("Details aus der aktuellen Seite ausgelesen.", "info")
                    
                    # Go back
                    back_btn = page.locator(selectors['back_button']).first
                    if back_btn.is_visible(timeout=2000):
                        back_btn.click()
                    else:
                        status_callback("Zurück-Button nicht sichtbar, nutze Browser-Zurück.", "warning")
                        page.go_back()
                        
                    # KORREKTUR: Hier direkt selectors['card'] statt card_selector nutzen!
                    page.wait_for_selector(selectors['card'], timeout=10000)
                
                scraped_data.append({
                    'Titel': title, 'Praxisort': location, 'Campus': campus, 'Studienstart': start_date,
                    'Über die Stelle': about, 'Das bieten wir': offer, 'Das bringst du mit': reqs
                })
                
            except Exception as e:
                status_callback(f"Fehler beim Auslesen von Job {i + 1}: {e}", "error")
                
            i += 1
            
        status_callback(f"Scraping beendet. {len(scraped_data)} Stellen ausgelesen.", "info")
        browser.close()
        
    return scraped_data