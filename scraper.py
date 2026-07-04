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
    status_callback(f"Bisher {last_card_count} Stellenanzeigen geladen. Erweitere Liste...", "info")
    
    no_change_count = 0
    while True:
        try:
            load_more_btn = page.locator(load_more_selector).first
            if load_more_btn.is_visible(timeout=1500):
                load_more_btn.click(force=True)
                page.wait_for_timeout(1500)
                
                current_card_count = page.locator(card_selector).count()
                if current_card_count > last_card_count:
                    status_callback(f"Karten geladen: {current_card_count}", "info")
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
    """Launches browser in a single thread, polls for successful login, and extracts jobs."""
    scraped_data = []
    
    with sync_playwright() as p:
        status_callback("Starte gesteuerten Chromium-Browser...", "info")
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        status_callback(f"Navigiere zu {url}...", "info")
        page.goto(url)
        
        card_selector = selectors['card']
        status_callback("🔑 Bitte logge dich jetzt im Browserfenster ein und gehe zur Stellenliste.", "warning")
        
        # Sichere Warteschleife innerhalb desselben Threads
        logged_in = False
        last_log_time = time.time()
        
        while not logged_in:
            if page.is_closed():
                status_callback("Browser wurde geschlossen. Scraping abgebrochen.", "error")
                return []
                
            try:
                card_count = page.locator(card_selector).count()
                if card_count > 0:
                    logged_in = True
                    status_callback(f"🎉 Login und Seitenstruktur erkannt! {card_count} Karten gefunden.", "info")
                    break
            except Exception:
                pass
                
            # Alle 5 Sekunden eine Erinnerung ins Streamlit UI schreiben, damit man sieht, dass es lebt
            if time.time() - last_log_time > 5:
                status_callback("Warte auf Login und Navigation zur Stellenliste...", "info")
                last_log_time = time.time()
                
            time.sleep(1)
            
        # Liste vollständig expandieren
        total_cards = expand_job_list(page, selectors, status_callback)
        status_callback(f"Starte Detail-Extraktion für alle {total_cards} Stellen...", "info")
        
        i = 0
        while i < total_cards:
            if page.is_closed():
                status_callback("Browser wurde während des Scrapings geschlossen.", "error")
                break
                
            try:
                page.set_default_timeout(10000)
                cards = page.locator(card_selector)
                current_count = cards.count()
                
                if current_count <= i:
                    status_callback(f"Liste komprimiert. Re-expandiere auf Index {i+1}...", "warning")
                    expand_job_list(page, selectors, status_callback)
                    cards = page.locator(card_selector)
                    if cards.count() <= i:
                        i += 1
                        continue
                
                card = cards.nth(i)
                card.scroll_into_view_if_needed()
                
                title = get_text_safe(card, selectors['title']) or "Unbekannter Titel"
                location = get_text_safe(card, selectors['location']) or "Nicht angegeben"
                campus = get_text_safe(card, selectors['campus']) or "Nicht angegeben"
                start_date = get_text_safe(card, selectors['start_date']) or "Nicht angegeben"
                
                # Granulares Live-Feedback für den Nutzer
                status_callback(f"[Karte {i + 1}/{total_cards}] Lese erfolgreich aus: '{title}'", "info")
                
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
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(1000)
                    
                    about = get_text_safe(page, selectors['detail_about'])
                    offer = get_text_safe(page, selectors['detail_offer'])
                    reqs = get_text_safe(page, selectors['detail_reqs'])
                    
                    back_btn = page.locator(selectors['back_button']).first
                    if back_btn.is_visible(timeout=2000):
                        back_btn.click()
                    else:
                        page.go_back()
                        
                    page.wait_for_selector(card_selector, timeout=5000)
                
                scraped_data.append({
                    'Titel': title, 'Praxisort': location, 'Campus': campus, 'Studienstart': start_date,
                    'Über die Stelle': about, 'Das bieten wir': offer, 'Das bringst du mit': reqs
                })
                
            except Exception as e:
                status_callback(f"Fehler bei Karte {i + 1}: {e}", "error")
                
            i += 1
            
        browser.close()
        
    return scraped_data