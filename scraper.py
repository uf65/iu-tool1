import time
from typing import List, Dict, Any, Callable
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

def get_text_safe(locator_parent, selector: str) -> str:
    """Safely retrieves inner text from a selector relative to a parent locator, returning empty string if not found."""
    try:
        element = locator_parent.locator(selector).first
        if element.is_visible(timeout=1000):
            return element.inner_text().strip()
    except Exception:
        pass
    return ""

def expand_job_list(page, selectors, status_callback: Callable[[str, str], None]) -> int:
    """
    Clicks the 'mehr anzeigen' button repeatedly to load all job postings.
    Returns the total number of jobs found.
    """
    card_selector = selectors['card']
    load_more_selector = selectors['load_more_button']
    
    last_card_count = page.locator(card_selector).count()
    status_callback(f"Bisher {last_card_count} Stellenanzeigen geladen. Suche nach 'mehr anzeigen'...", "info")
    
    no_change_count = 0
    while True:
        try:
            load_more_btn = page.locator(load_more_selector).first
            if load_more_btn.is_visible(timeout=2000):
                status_callback("Klicke auf 'mehr anzeigen'...", "info")
                load_more_btn.click(force=True)
                page.wait_for_timeout(2000) # Wait for network/DOM update
                
                current_card_count = page.locator(card_selector).count()
                status_callback(f"Karten geladen: {current_card_count}", "info")
                
                if current_card_count > last_card_count:
                    last_card_count = current_card_count
                    no_change_count = 0
                else:
                    no_change_count += 1
                    if no_change_count >= 3:
                        status_callback("Die Anzahl der Karten hat sich nach 3 Klicks nicht erhöht. Beende das Laden.", "warning")
                        break
            else:
                status_callback("Kein 'mehr anzeigen'-Button (mehr) sichtbar.", "info")
                break
        except Exception as e:
            status_callback(f"Fehler beim Klicken auf 'mehr anzeigen' oder Button nicht gefunden: {e}", "info")
            break
            
    return page.locator(card_selector).count()

def scrape_jobs(url: str, selectors: Dict[str, str], status_callback: Callable[[str, str], None]) -> List[Dict[str, Any]]:
    """
    Launches browser, waits for user login, expands list, and scrapes job details.
    """
    scraped_data = []
    
    with sync_playwright() as p:
        status_callback("Starte Browser (Chromium)...", "info")
        # Launch headed chromium so the user can interact
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        status_callback(f"Navigiere zu {url}...", "info")
        page.goto(url)
        
        # 1. Wait for login
        status_callback("Bitte logge dich im geöffneten Browserfenster ein und navigiere zur Stellenliste.", "warning")
        
        logged_in = False
        card_selector = selectors['card']
        while not logged_in:
            if page.is_closed():
                status_callback("Browser wurde geschlossen. Scraping abgebrochen.", "error")
                return []
                
            try:
                # If cards are visible, we consider ourselves logged in
                card_count = page.locator(card_selector).count()
                if card_count > 0:
                    logged_in = True
                    status_callback(f"Eingeloggt! {card_count} Stellenanzeigen auf Anhieb gefunden.", "info")
                    break
            except Exception:
                pass
            time.sleep(1)
            
        # 2. Expand list fully
        total_cards = expand_job_list(page, selectors, status_callback)
        status_callback(f"Insgesamt {total_cards} Stellenanzeigen geladen. Starte Detail-Scraping...", "info")
        
        # 3. Iterate through each card
        i = 0
        while i < total_cards:
            if page.is_closed():
                status_callback("Browser wurde geschlossen während des Scrapings.", "error")
                break
                
            status_callback(f"Scrape Job {i + 1} von {total_cards}...", "info")
            
            try:
                # Relocate cards because DOM might have changed after navigating back
                cards = page.locator(card_selector)
                current_count = cards.count()
                
                # If the list collapsed, re-expand it until we have enough cards
                if current_count <= i:
                    status_callback(f"Liste wurde zurückgesetzt (aktuell {current_count} Karten). Re-expandiere auf mindestens {i+1}...", "warning")
                    expand_job_list(page, selectors, status_callback)
                    cards = page.locator(card_selector)
                    current_count = cards.count()
                    if current_count <= i:
                        status_callback(f"Konnte Karte an Index {i} nach Re-Expandierung nicht finden. Überspringe.", "error")
                        i += 1
                        continue
                
                card = cards.nth(i)
                card.scroll_into_view_if_needed()
                
                # Extract basic info from the card
                title = get_text_safe(card, selectors['title'])
                location = get_text_safe(card, selectors['location'])
                campus = get_text_safe(card, selectors['campus'])
                start_date = get_text_safe(card, selectors['start_date'])
                
                status_callback(f"Stelle gefunden: '{title}' in {location} ({campus})", "info")
                
                # Click the card and check if it opens in a new tab or same tab
                about, offer, reqs = "", "", ""
                opened_new_tab = False
                
                try:
                    # Expect popup/tab within 2 seconds
                    with context.expect_page(timeout=2000) as new_page_info:
                        card.click()
                    
                    # If we reach here, it opened in a new tab
                    new_page = new_page_info.value
                    new_page.wait_for_load_state()
                    
                    about = get_text_safe(new_page, selectors['detail_about'])
                    offer = get_text_safe(new_page, selectors['detail_offer'])
                    reqs = get_text_safe(new_page, selectors['detail_reqs'])
                    
                    new_page.close()
                    opened_new_tab = True
                    status_callback("Details aus neuem Tab ausgelesen.", "info")
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
                        
                    page.wait_for_selector(card_selector, timeout=10000)
                
                # Append to our list
                scraped_data.append({
                    'Titel': title,
                    'Praxisort': location,
                    'Campus': campus,
                    'Studienstart': start_date,
                    'Über die Stelle': about,
                    'Das bieten wir': offer,
                    'Das bringst du mit': reqs
                })
                
            except Exception as e:
                status_callback(f"Fehler beim Auslesen von Job {i + 1}: {e}", "error")
                
            i += 1
            
        status_callback(f"Scraping beendet. {len(scraped_data)} Stellen ausgelesen.", "info")
        browser.close()
        
    return scraped_data
