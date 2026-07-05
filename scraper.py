import time
from typing import List, Dict, Any, Callable
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

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

def scrape_jobs(url: str, selectors: Dict[str, str], status_callback: Callable[[str, str], None]) -> List[Dict[str, Any]]:
    """
    Launches browser, verifies the login screen first, then waits for the user 
    to log in and navigates to the job board.
    """
    scraped_data = []
    
    with sync_playwright() as p:
        status_callback("Starte Browser (Chromium)...", "info")
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        status_callback(f"Navigiere zu {url}...", "info")
        page.goto(url)
        
        # --- ZWISCHENSCHRITT: LOGIN-SEITE ERKENNEN ---
        status_callback("Prüfe Verbindung und warte auf das Laden der Login-Maske...", "info")
        
        login_mask_detected = False
        while not login_mask_detected:
            if page.is_closed():
                status_callback("Browser wurde geschlossen. Abbruch.", "error")
                return []
                
            try:
                # Wir suchen nach der eindeutigen Logo-ID aus deinem HTML
                logo_visible = page.locator("#prompt-logo-center").is_visible(timeout=500)
                # Alternativ prüfen wir, ob die auth-URL aktiv ist
                if logo_visible or "auth.iu.org" in page.url:
                    login_mask_detected = True
                    status_callback("✅ Verbindung erfolgreich! Die IU-Login-Maske wurde im Browser erkannt.", "info")
                    break
            except Exception:
                pass
            time.sleep(1)
            
        # --- PHASE 2: JETZT ERST LOGIN AUFFORDERN ---
        status_callback("🔑 Bitte logge dich JETZT im Browserfenster ein und gehe zur Stellenliste.", "warning")
        
        logged_in = False
        last_log_time = time.time()
        
        while not logged_in:
            if page.is_closed():
                status_callback("Browser wurde geschlossen. Scraping abgebrochen.", "error")
                return []
                
            try:
                # STRATEGIE-WECHSEL: Wir suchen nach dem Text 'Praxisort', 
                # der auf JEDER Jobkarte existiert. Das durchbricht auch das Shadow-DOM!
                target_element = page.locator("p:has-text('Praxisort')").first
                
                if target_element.is_visible(timeout=500):
                    # Sicherheitshalber prüfen wir, ob wir wirklich auf der richtigen URL sind
                    if "/selfmatching" in page.url:
                        # Wir ermitteln die Anzahl der sichtbaren Karten über Playwrights internen Selektor
                        card_count = page.locator(selectors['card']).count()
                        
                        # Falls der CSS-Selektor wegen Shadow-DOM 0 liefert, 
                        # nutzen wir die Text-Locator als Fallback für die Anzahl
                        if card_count == 0:
                            card_count = page.locator("p:has-text('Praxisort')").count()
                            
                        logged_in = True
                        status_callback(f"🎉 Login erfolgreich! {card_count} Stellenanzeigen im Portal identifiziert.", "info")
                        break
            except Exception:
                pass
                
            if time.time() - last_log_time > 5:
                status_callback("Warte auf Abschluss des Logins (Suche nach Jobkarten-Inhalten)...", "info")
                last_log_time = time.time()
                
            time.sleep(1)
                        
        # 2. Liste vollständig expandieren
        page.wait_for_timeout(1000)
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
                    print("DEBUG about:", about)
                    print("DEBUG offer:", offer)
                    print("DEBUG reqs:", reqs)
                    
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
                    print("DEBUG2 about:", about)
                    print("DEBUG2 offer:", offer)
                    print("DEBUG2 reqs:", reqs)
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