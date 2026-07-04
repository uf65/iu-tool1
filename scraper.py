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

def init_browser(url: str) -> Dict[str, Any]:
    """Initializes the browser and navigates to the URL, returning the live objects."""
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto(url)
    return {
        "playwright": p,
        "browser": browser,
        "context": context,
        "page": page
    }

def expand_job_list(page, selectors, status_callback: Callable[[str, str], None]) -> int:
    """Clicks the 'mehr anzeigen' button repeatedly to load all job postings."""
    card_selector = selectors['card']
    load_more_selector = selectors['load_more_button']
    
    last_card_count = page.locator(card_selector).count()
    status_callback(f"Bisher {last_card_count} Stellenanzeigen auf der Seite geladen. Erweitere Liste...", "info")
    
    no_change_count = 0
    while True:
        try:
            load_more_btn = page.locator(load_more_selector).first
            if load_more_btn.is_visible(timeout=1500):
                load_more_btn.click(force=True)
                page.wait_for_timeout(1500)
                
                current_card_count = page.locator(card_selector).count()
                if current_card_count > last_card_count:
                    status_callback(f"Liste erweitert: {current_card_count} Karten sichtbar.", "info")
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

def extract_jobs_from_page(page, context, selectors: Dict[str, str], status_callback: Callable[[str, str], None]) -> List[Dict[str, Any]]:
    """Scrapes job details from the current page with granular status logs."""
    scraped_data = []
    card_selector = selectors['card']
    
    # Sofortige Überprüfung, ob das Ziel-Layout auffindbar ist
    try:
        card_count = page.locator(card_selector).count()
        if card_count == 0:
            status_callback("Keine Job-Karten mit der bekannten Struktur gefunden. Befindest du dich auf der korrekten Unterseite?", "error")
            return []
        status_callback(f"Seite erfolgreich identifiziert! {card_count} Job-Karten erkannt.", "info")
    except Exception as e:
        status_callback(f"Fehler bei Seitenprüfung: {e}", "error")
        return []

    # Liste vollständig laden
    total_cards = expand_job_list(page, selectors, status_callback)
    status_callback(f"Verarbeitung gestartet. Extrahiere Details für {total_cards} Stellen...", "info")
    
    i = 0
    while i < total_cards:
        if page.is_closed():
            status_callback("Browser wurde während des Prozesses geschlossen.", "error")
            break
            
        try:
            # Setze ein hartes Zeitlimit pro Karte, um endloses Hängen zu verhindern
            page.set_default_timeout(15000)
            
            cards = page.locator(card_selector)
            current_count = cards.count()
            
            if current_count <= i:
                status_callback(f"Liste komprimiert (nur noch {current_count} Karten). Re-expandiere auf Index {i+1}...", "warning")
                expand_job_list(page, selectors, status_callback)
                cards = page.locator(card_selector)
                if cards.count() <= i:
                    status_callback(f"Karte an Position {i+1} nicht mehr auffindbar. Überspringe.", "warning")
                    i += 1
                    continue
            
            card = cards.nth(i)
            card.scroll_into_view_if_needed()
            
            # Basis-Daten auslesen
            title = get_text_safe(card, selectors['title']) or "Unbekannter Titel"
            location = get_text_safe(card, selectors['location'])
            campus = get_text_safe(card, selectors['campus'])
            start_date = get_text_safe(card, selectors['start_date'])
            
            # Sofortiges Feedback für jede ausgelesene Karte im UI
            status_callback(f"[Karte {i + 1}/{total_cards}] Lese aus: '{title}' in {location or 'Unbekannter Ort'}", "info")
            
            # Detailseiten-Extraktion (Klick)
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
                # Fallback für In-Place-Navigation
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
                'Titel': title,
                'Praxisort': location,
                'Campus': campus,
                'Studienstart': start_date,
                'Über die Stelle': about,
                'Das bieten wir': offer,
                'Das bringst du mit': reqs
            })
            
        except Exception as e:
            status_callback(f"Fehler bei Karte {i + 1} ('{title}'): {e}", "error")
            
        i += 1
        
    return scraped_data