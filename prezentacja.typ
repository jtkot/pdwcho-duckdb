#import "@preview/touying:0.8.0": *
#import "@preview/numbly:0.1.0": numbly
#import themes.metropolis: *

#show: metropolis-theme.with(
  aspect-ratio: "16-9",
  footer: self => none,
  config-info(
    title: [DuckDB - bezserwerowa analiza danych z różnych źródeł],
    subtitle: [In-process OLAP w praktyce],
    author: [Jan Kot],
    date: [30.10.2026],
  ),
  config-colors(
    primary: rgb("#eab308"),
    primary-light: rgb("#fef08a"),
    secondary: rgb("#1e293b"),
    neutral-lightest: rgb("#f8fafc"),
    neutral-dark: rgb("#0f172a"),
    neutral-darkest: rgb("#020617"),
  ),
)

// Dodatkowe style dla bloków kodu i wyróżnień
#show raw.where(block: true): block.with(
  fill: rgb("#1e293b"),
  inset: 12pt,
  radius: 6pt,
  width: 100%,
)
#show raw.where(block: true): set text(fill: rgb("#f8fafc"), size: 0.85em)
#show raw.where(block: false): box.with(
  fill: rgb("#e2e8f0"),
  inset: (x: 4pt, y: 0pt),
  outset: (y: 3pt),
  radius: 3pt,
)

// Styl nagłówka tabeli
#show table.cell.where(y: 0): set text(fill: white, weight: "bold")
#set heading(numbering: (..nums) => {
  let list = nums.pos()
  if list.len() == 1 {
    numbering("1.", ..nums)
  }
})

#title-slide()

= Dlaczego wszyscy mówią o DuckDB?

== Problem "Big Data" w skali lokalnej

Większość codziennych zbiorów danych wcale nie wymaga klastra obliczeniowego.
#pause

#v(1em)
#grid(
  columns: (1fr, 1fr),
  gutter: 2em,
  [
    *Tradycyjne podejście:*
    - Ciężkie klastry (Spark, Snowflake) do plików rzędu kilku GB
    #pause
    - Wolny `pandas.read_csv()` zapychający pamięć RAM
    #pause
    - Konieczność stawiania serwera PostgreSQL do prostych zapytań
  ],
  pause,
  [
    *Nowa rzeczywistość:*
    - Laptopy mają dziś 16–64 GB RAM i szybkie dyski NVMe
    #pause
    - Procesory posiadają wiele rdzeni z instrukcjami SIMD
    #pause
    - *Wąskim gardłem stało się oprogramowanie, nie sprzęt*
  ],
)

== Czym jest DuckDB?

#v(0.5em)
- "SQLite dla analityki"
#pause
- *Bezserwerowy:* Jest biblioteką działającą wewnątrz procesu Twojej aplikacji
  (Python, R, Java, Node.js) lub jako pojedynczy plik wykonywalny CLI.
#pause
- *Zero konfiguracji:* Brak zewnętrznych zależności, demonów w tle czy
  zarządzania uprawnieniami.
#pause
- *Darmowy i otwartoźródłowy:* Licencja MIT.

== OLTP vs OLAP

- *OLTP* – Online Transaction Processing
#pause
- *OLAP* – Online Analytical Processing

#pause
#v(0.6em)

#set text(size: 0.8em)
#table(
  columns: (1.1fr, 1.4fr, 1.5fr),
  inset: 6.5pt,
  align: (left, left, left),
  fill: (x, y) => if y == 0 { rgb("#1e293b") } else if calc.odd(y) { rgb("#f1f5f9") } else { white },
  table.header([*Cecha*], [*OLTP*], [*OLAP*]),
  [Przeznaczenie], [Transakcje, stan aplikacji], [Analityka, agregacje, raporty],
  pause,
  [Profil zapytań], [Odczyt i zapis całych rekordów], [Analityka na milionach wierszy wybranych kolumn],
  pause,
  [Układ danych], [Wiersze], [*Kolumny*, kostki, tablice wielowymiarowe],
  pause,
  [Mechanizm wykonawczy], [*Wulkaniczny* (krotka po krotce)], [*Wektorowy* (paczki danych)],
  pause,
  [Typowe operacje], [`INSERT`, `UPDATE`, `SELECT` po ID], [`GROUP BY`, `JOIN`, `WINDOW`],
  pause,
  [Przykłady silników],
  [SQLite, PostgreSQL, MySQL, SQL Server],
  [DuckDB, ClickHouse, Apache Pinot, Snowflake, BigQuery],
)

= Architektura: Dlaczego to jest tak szybkie?

== Dwa filary wydajności

#grid(
  columns: (1fr, 1fr),
  gutter: 2em,
  [
    === 1. Przechowywanie kolumnowe
    - Czytamy z dysku *tylko te kolumny*, które są w zapytaniu `SELECT`.
    #pause
    - Doskonała kompresja (dane tego samego typu leżą obok siebie).
    #pause
    - Przeskakiwanie całych bloków danych dzięki statystykom min/max (*Zone Maps*).
  ],
  pause,
  [
    === 2. Silnik wektoryzowany
    - Dane przetwarzane w paczkach (wektorach, domyślnie po 2048 elementów).
    #pause
    - Wektory mieszczą się bezpośrednio w pamięci podręcznej procesora (*L1/L2 Cache*).
    #pause
    - Wykorzystanie instrukcji *SIMD* (jedna instrukcja CPU operuje na wielu danych naraz).
  ],
)

== Zarządzanie pamięcią
#v(1em)
*Out-of-Core Processing* - DuckDB ma możliwość przetwarzania danych w wolumenach
znacznie przekraczających dostępną pamięć RAM.

#pause
#v(0.5em)
Przykład: Analiza 30 GB danych na urządzeniu z 16 GB RAM
#pause
- *Pandas:* `MemoryError` lub drastyczne spowolnienie przez konieczność korzystania ze swap.
#pause
- *DuckDB:* Automatyczne strumieniowanie i zrzucanie danych pośrednich na dysk.

= Bezserwerowa analiza z różnych źródeł

== Bezproblemowa integracja z istniejącymi źródłami danych

DuckDB natywnie rozumie najpopularniejsze formaty i protokoły:

#v(0.5em)
- *Pliki lokalne:* CSV, Parquet, JSON (automatyczna detekcja schematu,
  obsługa wieloplikowa np. `logs/*.parquet`).
#pause
- *Zdalne systemy plików (`httpfs`):* Czytanie bezpośrednio z AWS S3, GCS,
  Azure Blob Storage lub zwykłych adresów HTTP/HTTPS.
#pause
- *Bazy relacyjne:* Bezpośrednie podłączanie żywych baz *PostgreSQL*, *MySQL*
  oraz *SQLite*.
#pause
- *Formaty Lakehouse:* Natywny odczyt tabel *Apache Iceberg* oraz *Delta Lake*.

== Optymalizacja zapytań: Pushdown

Przeniesienie logiki zawężania zbioru danych bezpośrednio do źródła (*Pushdown*):

#v(0.6em)
- *Projection Pushdown:* rzutowanie i dobór kolumn (`SELECT user_id, amount`) – czytamy tylko wymagane atrybuty.
#pause
- *Predicate Pushdown:* filtrowanie (`WHERE country = 'PL'`) – odrzucanie rekordów przed załadowaniem do pamięci.

#pause
#v(0.6em)
*Korzyści:*
#pause
- Ograniczenie transferu sieciowego i operacji wejścia/wyjścia (I/O).
#pause
- Znacznie mniejsze zużycie pamięci RAM i krótszy czas wykonania.

== Pushdown w praktyce: Zdalny plik na AWS S3

Zapytanie do 100-gigabajtowego pliku Parquet w chmurze S3:

```sql
SELECT user_id, amount 
FROM 's3://bucket/transactions_2025.parquet' 
WHERE country = 'PL';
```

#pause
DuckDB *nie pobiera* całego pliku przez sieć:
#pause
+ Odczytuje metadane pliku Parquet.
#pause
+ Sprawdza które grupy wierszy zawierają `country = 'PL'`.
#pause
+ Pobiera przez sieć wyłącznie bajty dla kolumn `user_id` i `amount` z pasujących bloków.

== Integracja z popularnymi językami programowania

DuckDB udostępnia gotowe biblioteki połączeniowe dla środowisk:
#pause
- *Python*, *R* – środowiska analityczne i Data Science
#pause
- *Node.js*, *Java*, *Go*, *C/C++*, *Rust* – backendy i aplikacje natywne
#pause
- *ODBC* – uniwersalny sterownik bazodanowy

== Friendly SQL

DuckDB rozszerza standardowy SQL o konstrukcje przyspieszające codzienną pracę:

- `FROM` na początku zapytania:
  `FROM 'dane.csv' SELECT kolumna1, kolumna2;`
#pause
- `GROUP BY ALL` - koniec z powtarzaniem nazw kolumn z sekcji `SELECT`.
#pause
- `SELECT * EXCLUDE (haslo, pesel)` - łatwe pomijanie niechcianych kolumn.
#pause
- `SELECT * REPLACE (kwota * 1.23 AS kwota)` - modyfikacja kolumn w locie.
#pause
- `DESCRIBE` oraz `SUMMARIZE` - natychmiastowe profilowanie statystyczne zbioru danych.

== Współpraca z ekosystemem analitycznym języka Python

DuckDB wymienia dane z bibliotekami takimi jak *Pandas*, *Polars*, czy
*Apache Arrow* bez kopiowania pamięci (*Zero-Copy*).

#pause
```python
import duckdb
import polars as pl

df = pl.read_parquet("duze_dane.parquet")

# DuckDB widzi zmienną 'df' bezpośrednio w przestrzeni nazw Pythona!
wynik = duckdb.sql("""
    SELECT kategoria, AVG(cena) as srednia_cena
    FROM df
    GROUP BY kategoria
""").pl() # Zwraca wynik z powrotem jako DataFrame Polars
```

= Podsumowanie

== Kiedy używać DuckDB, a kiedy nie?

#grid(
  columns: (1fr, 1fr),
  gutter: 2em,
  [
    === Świetny wybór, gdy:
    - Analizujesz dane lokalnie (Data Science, eksploracja, prototypowanie).
    #pause
    - Budujesz szybkie potoki ekstrakcji danych (ETL/ELT) na pojedynczej maszynie (zamiast ciężkiego Sparka).
    #pause
    - Potrzebujesz wbudować szybki silnik analityczny wewnątrz aplikacji lub API.
    #pause
    - Chcesz konwertować dane między formatami (np. CSV $->$ Parquet).
  ],
  pause,
  [
    === Zły wybór, gdy:
    - Budujesz system transakcyjny o wysokiej współbieżności zapisu.
    #pause
    - Wielu użytkowników musi jednocześnie zapisywać dane do tego samego pliku.
    #pause
    - Twoje dane przekraczają wielokrotnie pojemność dysku pojedynczej dużej maszyny (setki terabajtów).
  ],
)

#slide(config: config-page(header: none))[
  *Przydatne linki:*
  - Dokumentacja: `https://duckdb.org/docs`
  - Wypróbuj w przeglądarce (Wasm): `https://shell.duckdb.org`
]
