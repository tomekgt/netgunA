# Monitor nowych ogłoszeń — NetGun.pl

Codziennie sprawdza wybrane kategorie na [netgun.pl](https://www.netgun.pl/ogloszenia)
(domyślnie: **Pistolety**) i pokazuje na jednej stronie tylko **nowe** ogłoszenia,
których wcześniej nie było — bez konieczności ręcznego przeglądania.

Działa w całości za darmo na GitHub Actions + GitHub Pages. Nic nie musisz
trzymać włączonego na własnym komputerze.

## Jak to działa

1. `scripts/check_new_listings.py` przegląda pierwsze kilka stron danej
   kategorii (domyślnie 5 stron × 20 ogłoszeń).
2. Porównuje znalezione ID ogłoszeń z listą już widzianych
   (`data/seen_listings.json`).
3. Nowe ogłoszenia dopisuje do historii i generuje `docs/index.html`.
4. Workflow GitHub Actions (`.github/workflows/daily-check.yml`) uruchamia
   to raz dziennie i commituje zmiany z powrotem do repozytorium.
5. GitHub Pages serwuje `docs/index.html` pod stałym adresem.

## Instalacja (10 minut, jednorazowo)

1. **Załóż nowe repozytorium na GitHub** (może być prywatne) i wgraj do niego
   całą zawartość tego folderu (najprościej: przeciągnij pliki w interfejsie
   GitHub, albo `git init` + `git add .` + `git commit` + `git push`, jeśli
   znasz Gita).

2. **Włącz GitHub Pages:**
   - Wejdź w `Settings` → `Pages` w swoim repozytorium.
   - W `Source` wybierz `Deploy from a branch`.
   - Branch: `main`, folder: `/docs`.
   - Zapisz. Po chwili GitHub poda Ci adres strony (coś w stylu
     `https://twoja-nazwa.github.io/nazwa-repo/`) — to jest link, który
     otwierasz, żeby zobaczyć nowe ogłoszenia.

3. **Sprawdź uprawnienia workflow (zwykle domyślnie OK):**
   - `Settings` → `Actions` → `General` → sekcja `Workflow permissions`.
   - Zaznacz `Read and write permissions`. Zapisz.

4. **Uruchom pierwszy raz ręcznie**, żeby nie czekać do jutra:
   - Zakładka `Actions` w repozytorium.
   - Wybierz workflow `Sprawdź nowe ogłoszenia NetGun`.
   - Kliknij `Run workflow` → `Run workflow`.
   - Poczekaj ~1 minutę, odśwież stronę z Pages.

Od teraz workflow uruchamia się automatycznie codziennie o 6:00 UTC
(ok. 7-8 rano czasu polskiego). Pierwsze uruchomienie potraktuje **wszystkie**
znalezione ogłoszenia jako "nowe" (bo baza jest pusta) — to normalne,
kolejne dni pokażą już tylko prawdziwe nowości.

## Dodawanie kolejnych kategorii

W pliku `scripts/check_new_listings.py` znajdziesz słownik:

```python
CATEGORIES = {
    "pistolety": "Pistolety",
}
```

Żeby dodać np. karabiny, dopisz kolejny wiersz, używając slugu z adresu URL
kategorii na netgun.pl:

```python
CATEGORIES = {
    "pistolety": "Pistolety",
    "karabiny": "Karabiny",
}
```

Dostępne slugi kategorii na netgun.pl: `pistolety`, `rewolwery`, `karabiny`,
`gladkolufowa`, `lr22`, `bron-czarnoprochowa`, `czesci-i-tuning-broni`,
`amunicja-elaboracja`, `optyka-celownicza`, `szafy-sejfy`,
`akcesoria-strzeleckie`, `zabudowy`, `pojazdy-akcesoria`, `pozostale`.

## Uwagi

- Skrypt sprawdza domyślnie 5 pierwszych stron każdej kategorii dziennie
  (100 ogłoszeń). Jeśli kategoria jest bardzo aktywna, możesz zwiększyć
  `PAGES_PER_CATEGORY` na początku skryptu.
- Struktura strony netgun.pl może się kiedyś zmienić — jeśli po jakimś
  czasie strona przestanie pokazywać nowości mimo realnych nowych ogłoszeń,
  daj znać, poprawię parser.
- Historia na stronie pokazuje domyślnie ostatnie 14 dni (`DAYS_OF_HISTORY`).
