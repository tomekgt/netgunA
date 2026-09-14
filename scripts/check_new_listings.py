#!/usr/bin/env python3
"""
Sprawdza wybrane kategorie na NetGun.pl, wykrywa NOWE ogłoszenia
(których jeszcze nie widzieliśmy) i generuje statyczną stronę HTML
z podsumowaniem.
 
Stan (które ogłoszenia już widzieliśmy) trzymany jest w pliku
data/seen_listings.json, który jest commitowany z powrotem do repo
przez workflow GitHub Actions - dzięki temu "pamięć" przechowywana
jest za darmo w samym repozytorium.
"""
 
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
 
import requests
from bs4 import BeautifulSoup
 
BASE_URL = "https://www.netgun.pl"
 
# Które kategorie śledzimy: slug -> ładna nazwa do wyświetlenia.
# Żeby dodać kolejną kategorię, wystarczy dopisać wpis do słownika,
# używając slugów widocznych w adresie URL kategorii na netgun.pl.
CATEGORIES = {
    "pistolety": "Pistolety",
}
 
# Ile pierwszych stron danej kategorii sprawdzamy przy każdym uruchomieniu.
# Strona wyświetla nowe/promowane ogłoszenia w pierwszych wynikach, ale
# promowane ogłoszenia bywają "podbijane" i mieszają kolejność, dlatego
# sprawdzamy kilka pierwszych stron, a nie tylko pierwszą.
PAGES_PER_CATEGORY = 5
 
# Ile dni historii pokazujemy na wygenerowanej stronie.
DAYS_OF_HISTORY = 14
 
ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "seen_listings.json"
OUTPUT_HTML = ROOT / "docs" / "index.html"
 
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
 
# Dopasowuje linki do szczegółów ogłoszenia, np.:
# /pistolety/sprzedam/162008-sprzedam-pistolet
# /pistolety/kupie/162003-kupie-micro-roni-do-cz-p10c
# (dopasowujemy samą ŚCIEŻKĘ, po ewentualnym usunięciu domeny - patrz normalize_href)
LISTING_HREF_RE = re.compile(r"^/(?P<category>[a-z\-]+)/(?P<kind>sprzedam|kupie)/(?P<id>\d+)-")
 
DOMAIN_PREFIXES = (
    "https://www.netgun.pl",
    "http://www.netgun.pl",
    "https://netgun.pl",
    "http://netgun.pl",
)
 
 
def normalize_href(href):
    """Zwraca samą ścieżkę, niezależnie od tego czy href był względny
    (/pistolety/...) czy pełny (https://www.netgun.pl/pistolety/...)."""
    for prefix in DOMAIN_PREFIXES:
        if href.startswith(prefix):
            return href[len(prefix):]
    return href
 
 
def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"seen": {}, "history": []}
 
 
def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
 
 
def fetch_page(category_slug, page_number):
    url = f"{BASE_URL}/{category_slug}"
    if page_number > 1:
        url += f"?page={page_number}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    print(f"    [debug] GET {url} -> status {resp.status_code}, {len(resp.text)} znaków")
    resp.raise_for_status()
    return resp.text
 
 
def extract_price(container_text):
    """Wyciąga ostatnią liczbę z 'zł' z bloku tekstu, np. '2500 zł 2000 zł' -> '2000 zł'."""
    matches = re.findall(r"([\d][\d\s]{0,9})\s?zł", container_text)
    if not matches:
        return None
    cleaned = matches[-1].replace("\xa0", " ").strip()
    return f"{cleaned} zł"
 
 
def extract_condition(container_text):
    if "Używany" in container_text:
        return "Używany"
    if "Nowy" in container_text:
        return "Nowy"
    return None
 
 
def find_listing_container(anchor):
    """Idzie w górę drzewa DOM aż znajdzie kontener pojedynczego ogłoszenia
    (taki, który zawiera obrazek - miniaturkę)."""
    node = anchor
    for _ in range(6):
        if node.parent is None:
            break
        node = node.parent
        if node.find("img") is not None:
            return node
    return anchor.parent or anchor
 
 
def parse_listings_from_html(html, category_slug, debug=False):
    soup = BeautifulSoup(html, "html.parser")
    listings = {}
 
    all_links = soup.find_all("a", href=True)
    matched_any_category = 0
 
    for a in all_links:
        path = normalize_href(a["href"])
        m = LISTING_HREF_RE.match(path)
        if not m:
            continue
        matched_any_category += 1
        if m.group("category") != category_slug:
            continue
 
        listing_id = m.group("id")
        title = a.get_text(strip=True)
        if not title:
            continue  # linki-obrazki bez tekstu pomijamy, złapiemy tę samą ofertę z linku tekstowego
 
        if listing_id in listings:
            continue  # ten sam listing bywa linkowany dwa razy (obrazek + tytuł)
 
        container = find_listing_container(a)
        container_text = container.get_text(" ", strip=True)
 
        img_tag = container.find("img")
        thumbnail = img_tag["src"] if img_tag and img_tag.get("src") else None
        if thumbnail and thumbnail.startswith("/"):
            thumbnail = BASE_URL + thumbnail
 
        listings[listing_id] = {
            "id": listing_id,
            "title": title,
            "url": BASE_URL + path,
            "kind": m.group("kind"),
            "price": extract_price(container_text),
            "condition": extract_condition(container_text),
            "thumbnail": thumbnail,
        }
 
    if debug:
        print(
            f"    [debug] linków <a> na stronie: {len(all_links)}, "
            f"pasujących do wzorca ogłoszenia (dowolna kategoria): {matched_any_category}, "
            f"z kategorii '{category_slug}': {len(listings)}"
        )
 
    return listings
 
 
def scan_category(category_slug, pages):
    all_listings = {}
    for page in range(1, pages + 1):
        try:
            html = fetch_page(category_slug, page)
        except requests.RequestException as e:
            print(f"  Błąd pobierania {category_slug} strona {page}: {e}", file=sys.stderr)
            break
        found = parse_listings_from_html(html, category_slug, debug=(page == 1))
        if not found:
            # pusta strona - prawdopodobnie koniec ogłoszeń w tej kategorii
            if page == 1:
                # Nic nie znaleziono nawet na pierwszej stronie - zrzuć fragment
                # HTML do logów, żeby dało się zdiagnozować dlaczego.
                print("  [debug] Nie znaleziono NIC na 1. stronie. Pierwsze 1500 znaków HTML:")
                print(html[:1500])
            break
        all_listings.update(found)
        time.sleep(1)  # uprzejmość wobec serwera
    return all_listings
 
 
def build_html(state):
    history = state.get("history", [])
    history = history[-DAYS_OF_HISTORY:]
    history_sorted = list(reversed(history))
 
    now_str = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
 
    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html lang='pl'><head><meta charset='utf-8'>")
    parts.append("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    parts.append("<title>Nowe ogłoszenia — NetGun.pl</title>")
    parts.append("""
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 900px;
         margin: 0 auto; padding: 20px; line-height: 1.4; }
  h1 { font-size: 1.4rem; }
  h2 { font-size: 1.1rem; margin-top: 2rem; border-bottom: 1px solid #8884; padding-bottom: .3rem; }
  .meta { color: #888; font-size: .85rem; margin-bottom: 1.5rem; }
  .item { display: flex; gap: 12px; padding: 10px 0; border-bottom: 1px solid #8882; }
  .item img { width: 80px; height: 80px; object-fit: cover; border-radius: 6px; flex-shrink: 0; background:#8881;}
  .item .title { font-weight: 600; }
  .item .title a { color: inherit; text-decoration: none; }
  .item .title a:hover { text-decoration: underline; }
  .price { font-weight: 600; }
  .tag { display: inline-block; font-size: .75rem; padding: 1px 7px; border-radius: 10px;
         background: #8882; margin-right: 4px; }
  .empty { color: #888; font-style: italic; }
</style>
""")
    parts.append("</head><body>")
    parts.append("<h1>🔫 Nowe ogłoszenia — NetGun.pl</h1>")
    parts.append(f"<div class='meta'>Ostatnie sprawdzenie: {now_str}</div>")
 
    if not history_sorted:
        parts.append("<p class='empty'>Brak jeszcze danych — poczekaj na pierwsze uruchomienie.</p>")
 
    for day in history_sorted:
        date = day["date"]
        items = day["items"]
        parts.append(f"<h2>{date} — {len(items)} nowych</h2>")
        if not items:
            parts.append("<p class='empty'>Brak nowych ogłoszeń tego dnia.</p>")
            continue
        for it in items:
            thumb = it.get("thumbnail") or ""
            price = it.get("price") or "—"
            condition = it.get("condition")
            category = CATEGORIES.get(it.get("category", ""), it.get("category", ""))
            kind = "Sprzedam" if it.get("kind") == "sprzedam" else "Kupię"
            parts.append("<div class='item'>")
            if thumb:
                parts.append(f"<img src='{thumb}' alt=''>")
            else:
                parts.append("<div style='width:80px;height:80px;flex-shrink:0;'></div>")
            parts.append("<div>")
            parts.append(
                f"<div><span class='tag'>{category}</span><span class='tag'>{kind}</span>"
                + (f"<span class='tag'>{condition}</span>" if condition else "")
                + "</div>"
            )
            parts.append(f"<div class='title'><a href='{it['url']}' target='_blank' rel='noopener'>{it['title']}</a></div>")
            parts.append(f"<div class='price'>{price}</div>")
            parts.append("</div></div>")
 
    parts.append("</body></html>")
    return "\n".join(parts)
 
 
def main():
    state = load_state()
    state.setdefault("seen", {})
    state.setdefault("history", [])
 
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    todays_new_items = []
 
    for slug, pretty_name in CATEGORIES.items():
        print(f"Sprawdzam kategorię: {pretty_name} ({slug})")
        is_new_category = slug not in state["seen"]
        seen_ids = state["seen"].setdefault(slug, {})
        current = scan_category(slug, PAGES_PER_CATEGORY)
        print(f"  Znaleziono {len(current)} ogłoszeń na {PAGES_PER_CATEGORY} stronach.")
 
        if is_new_category:
            # Pierwsze uruchomienie dla tej kategorii: ustalamy punkt zerowy
            # (zapamiętujemy co już istnieje), ale NIE pokazujemy tego jako
            # "nowości" na stronie - to by tylko zaśmieciło listę.
            for listing_id, info in current.items():
                seen_ids[listing_id] = {
                    "title": info["title"],
                    "first_seen": today,
                }
            print(f"  Nowa kategoria — ustalono punkt startowy ({len(current)} ogłoszeń), "
                  f"nie pokazuję ich jako nowości.")
            continue
 
        for listing_id, info in current.items():
            if listing_id not in seen_ids:
                info["category"] = slug
                todays_new_items.append(info)
                seen_ids[listing_id] = {
                    "title": info["title"],
                    "first_seen": today,
                }
 
    print(f"Nowych ogłoszeń dzisiaj: {len(todays_new_items)}")
 
    # Dopisz dzisiejszy wpis do historii (albo zaktualizuj, jeśli już
    # skrypt uruchamiano dziś wcześniej).
    history = state["history"]
    if history and history[-1]["date"] == today:
        history[-1]["items"].extend(todays_new_items)
    else:
        history.append({"date": today, "items": todays_new_items})
    state["history"] = history[-DAYS_OF_HISTORY:]
 
    save_state(state)
 
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(build_html(state))
 
    print(f"Zapisano stronę: {OUTPUT_HTML}")
 
 
if __name__ == "__main__":
    main()

