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

def expand_job_list_old(page, selectors, status_callback: Callable[[str, str], None]) -> int:
    """Clicks the 'mehr anzeigen' button repeatedly to load all job postings."""
    
    print("In expand:", id(page))
    
    print("=== expand_job_list ===")
    print("page.url =", page.url)
    print("selector =", selectors["card"])

    print("cards:", page.locator(selectors["card"]).count())
    print("relative:", page.locator("div.relative.cursor-pointer").count())
    print("links:", page.locator("a[href^='/selfmatching/']").count())
    
    card_selector = selectors['card']
    load_more_selector = selectors['load_more_button']
    
    try:
        page.locator(card_selector).first.wait_for(state="attached", timeout=5000)
    except Exception:
        print("DEBUG: Keine Karte innerhalb von 5 Sekunden im DOM angehängt.")

    last_card_count = page.locator(card_selector).count()
    status_callback(f"Bisher {last_card_count} Stellenanzeigen geladen. Suche nach 'mehr anzeigen'...", "info")
    
    no_change_count = 0
    while True:
        try:
            load_more_btn = page.locator(load_more_selector).first
            print(f"DEBUG: load_more_btn ist sichtbar? {load_more_btn.is_visible(timeout=2000)}")
            if load_more_btn.is_visible(timeout=2000):
                # load_more_btn.click(force=True)
                # page.wait_for_timeout(2000)
                
                # current_card_count = page.locator(card_selector).count()
                old_count = page.locator(card_selector).count()

                load_more_btn.click()

                page.wait_for_function(
                    """([selector, oldCount]) => {
                        return document.querySelectorAll(selector).length > oldCount;
                    }""",
                    arg=[card_selector, old_count],
                    timeout=10000
                )

                current_card_count = page.locator(card_selector).count()
                print(f"DEBUG: {current_card_count} Karten gefunden.")
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

def expand_job_list(page, selectors, status_callback: Callable[[str, str], None], target_count: int = None) -> int:
    """Clicks the 'mehr anzeigen' button until all or target_count jobs are loaded."""
    card_selector = selectors['card']
    load_more_selector = selectors['load_more_button']
    
    try:
        page.locator(card_selector).first.wait_for(state="attached", timeout=5000)
    except Exception:
        print("DEBUG: Keine Karte innerhalb von 5 Sekunden im DOM angehängt.")

    while True:
        current_card_count = page.locator(card_selector).count()
        
        # 🚀 ABBRUCH-BEDINGUNG: Wenn das Ziel erreicht ist, hören wir sofort auf zu klicken!
        if target_count is not None and current_card_count >= target_count:
            break
            
        try:
            load_more_btn = page.locator(load_more_selector).first
            print(f"DEBUG: load_more_btn ist sichtbar? {load_more_btn.is_visible(timeout=2000)}")
            if load_more_btn.is_visible(timeout=2000):
                old_count = page.locator(card_selector).count()

                load_more_btn.click()

                page.wait_for_function(
                    """([selector, oldCount]) => {
                        return document.querySelectorAll(selector).length > oldCount;
                    }""",
                    arg=[card_selector, old_count],
                    timeout=10000
                )

                current_card_count = page.locator(card_selector).count()
                print(f"DEBUG: {current_card_count} Karten gefunden.")
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
        
        status_callback(f"Navigiere zu {url}...", "info")

        # Für lokales Chromium-Scraping (headless=False)
        context = browser.new_context(
            # Entweder komplett weglassen oder einen echten Chrome-String nutzen:
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900}
        )
        page = context.new_page()

        # 🚀 Der abgehärtete Chromium Shadow-DOM-Hack
        page.add_init_script("""
            (function() {
                const originalAttachShadow = Element.prototype.attachShadow;
                Object.defineProperty(Element.prototype, 'attachShadow', {
                    value: function(init) {
                        // Erzwinge 'open', egal was das Portal anfordert
                        return originalAttachShadow.call(this, Object.assign({}, init, { mode: 'open' }));
                    },
                    configurable: true,
                    writable: true
                });
            })();
        """)

        page.set_default_timeout(30000)

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
        print("relative:", page.locator("div.relative.cursor-pointer").count())
        print("links:", page.locator("a[href^='/selfmatching/']").count())
        print("title:", page.locator("p.text-xl").count())
        print("Vor expand:", id(page))
        print("Vor expand:", page.locator("div.relative.cursor-pointer").count())
        total_cards = expand_job_list(page, selectors, status_callback)
        print("Nach expand:", page.locator("div.relative.cursor-pointer").count())

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
                    print(f"({i}) relative:", page.locator("div.relative.cursor-pointer").count())
                    print(f"({i}) links:", page.locator("a[href^='/selfmatching/']").count())
                    print(f"({i}) title:", page.locator("p.text-xl").count())
                    print("Vor expand:", id(page))
                    print("Vor expand:", page.locator("div.relative.cursor-pointer").count())
                    expand_job_list(page, selectors, status_callback, target_count=i+1)
                    print("Nach expand:", page.locator("div.relative.cursor-pointer").count())
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

                # Prüfen, ob das gefüllte Herz-Symbol im HTML der Karte existiert
                has_filled_heart = card.locator("symbol#icon-heart-filled, path[fill='#3772FF']").count() > 0

                # Herzsymbol für Status_callback
                is_favorite = ""
                if has_filled_heart:
                    is_favorite = "⭐"
                
                status_callback(f"Stelle gefunden: '{title}' in {location} ({campus}) {is_favorite}", " info")
                
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
                    'Über die Stelle': about, 'Das bieten wir': offer, 'Das bringst du mit': reqs,
                    "Favorit": True if has_filled_heart else False
                })
                
            except Exception as e:
                status_callback(f"Fehler beim Auslesen von Job {i + 1}: {e}", "error")
                
            i += 1
            
        status_callback(f"Scraping beendet. {len(scraped_data)} Stellen ausgelesen.", "info")
        browser.close()
        
    return scraped_data