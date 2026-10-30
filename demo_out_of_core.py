#!/usr/bin/env python3

# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "duckdb>=2.0.0",
#     "pandas>=3.1.0",
#     "psutil>=7.2.2",
#     "tabulate>=0.10.0",
# ]
# ///

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import multiprocessing as mp
from pathlib import Path

# Kolory ANSI do estetycznej prezentacji
GREEN = "\033[1;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[1;36m"
RED = "\033[1;31m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_header(title: str):
    print(f"\n{CYAN}{'='*72}{RESET}")
    print(f"{BOLD}{title}{RESET}")
    print(f"{CYAN}{'='*72}{RESET}")


def get_parquet_row_count(parquet_file: Path) -> int | None:
    """Odczytuje liczbę wierszy z metadanych pliku Parquet (błyskawicznie, bez skanowania danych)."""
    try:
        import duckdb
        res = duckdb.sql(f"SELECT COUNT(*) FROM '{parquet_file.as_posix()}'").fetchone()
        if res and res[0] is not None:
            return int(res[0])
    except Exception:
        pass

    try:
        cmd = f"duckdb -dark-mode -c \"SELECT COUNT(*) FROM '{parquet_file.as_posix()}';\""
        out = subprocess.check_output(cmd, shell=True, text=True)
        for line in out.splitlines():
            clean = line.strip("│ \t\r\n")
            if clean.isdigit():
                return int(clean)
    except Exception:
        pass

    return None


def ensure_dataset(parquet_file: Path, num_rows: int, force: bool = False):
    """Generuje plik Parquet, jeśli nie istnieje, wymuszono regenerację lub liczba wierszy się nie zgadza."""
    if parquet_file.exists() and not force:
        size_mb = parquet_file.stat().st_size / (1024 * 1024)
        existing_rows = get_parquet_row_count(parquet_file)

        if existing_rows is not None and existing_rows == num_rows:
            print(f"  ℹ️  Użycie istniejącego pliku: {BOLD}{parquet_file.name}{RESET} ({size_mb:.1f} MB, {existing_rows:,} wierszy - zgodne z parametrami)")
            return
        elif existing_rows is not None:
            print(f"  ⚠️  Plik {BOLD}{parquet_file.name}{RESET} istnieje ({size_mb:.1f} MB), ale zawiera {existing_rows:,} wierszy (oczekiwano: {num_rows:,}).")
            print(f"  🔄 Wymagana regeneracja pliku...")
        else:
            print(f"  ⚠️  Plik {BOLD}{parquet_file.name}{RESET} istnieje, ale nie udało się zweryfikować liczby wierszy.")
            print(f"  🔄 Regeneracja pliku...")
    elif force:
        print(f"  🔄 Wymuszono ponowne wygenerowanie pliku (--regenerate)...")

    print(f"  ⏳ Generowanie syntetycznego pliku Parquet ({num_rows:,} wierszy)...")
    try:
        import duckdb
        duckdb.sql(f"""
            COPY (
                SELECT 
                    range AS order_id,
                    (range % 500000)::INT AS category_id,
                    'klient_' || (range % 1000000) AS customer_id,
                    ROUND(random() * 500, 2) AS amount
                FROM range({num_rows})
            ) TO '{parquet_file.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD);
        """)
    except Exception:
        cmd = f"""duckdb -dark-mode -c "
            COPY (
                SELECT 
                    range AS order_id,
                    (range % 500000)::INT AS category_id,
                    'klient_' || (range % 1000000) AS customer_id,
                    ROUND(random() * 500, 2) AS amount
                FROM range({num_rows})
            ) TO '{parquet_file.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD);
        " """
        subprocess.run(cmd, shell=True, check=True)

    size_mb = parquet_file.stat().st_size / (1024 * 1024)
    print(f"  ✅ Wygenerowano: {BOLD}{parquet_file.name}{RESET} ({size_mb:.1f} MB na dysku, {num_rows:,} wierszy)")


def memory_monitor(pid: int, stop_event: threading.Event, peak_container: list):
    """Monitoruje szczytowe zużycie pamięci RSS procesu."""
    try:
        import psutil
        process = psutil.Process(pid)
        peak = 0
        while not stop_event.is_set():
            try:
                mem = process.memory_info().rss
                peak = max(peak, mem)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            time.sleep(0.02)
        peak_container.append(peak)
    except ImportError:
        peak_container.append(0)


def _pandas_worker(parquet_file: str, result_queue: mp.Queue):
    """Kod Pandas wykonywany w osobnym procesie OS."""
    import time
    import pandas as pd

    try:
        t0 = time.time()
        print("   -> [Pandas] Wczytywanie całego pliku Parquet do RAM...")
        df = pd.read_parquet(parquet_file, columns=["category_id", "amount"])
        t_read = time.time() - t0
        mem_mb = df.memory_usage(deep=True).sum() / (1024 * 1024)
        print(f"   -> [Pandas] Plik wczytany w {t_read:.2f}s. Liczba wierszy: {len(df):,}")
        print(f"   -> [Pandas] Rozmiar DataFrame w pamięci: {mem_mb:.1f} MB")

        print("   -> [Pandas] Obliczanie agregacji (GROUP BY category_id)...")
        t1 = time.time()
        res = df.groupby("category_id")["amount"].agg(["count", "mean", "sum"]).reset_index()
        res = res.sort_values(by="sum", ascending=False).head(5)
        t_agg = time.time() - t1
        total_time = time.time() - t0

        print(f"   -> [Pandas] Sukces w {total_time:.2f}s (agregacja: {t_agg:.2f}s)")
        print("   -> Top 3 wyniki:")
        for _, row in res.head(3).iterrows():
            print(f"      kat: {int(row['category_id'])} | zamówień: {int(row['count'])} | suma: {row['sum']:.2f}")

        result_queue.put({"success": True, "duration": total_time, "error": None})
    except Exception as e:
        result_queue.put({"success": False, "duration": 0.0, "error": str(e)})


def run_pandas_test(parquet_file: Path, num_rows: int, memory_limit: str):
    """Uruchamia test w Pandas w osobnym procesie, aby zmierzyć szczytowy RAM."""
    print_header("1. PANDAS: Eager In-Memory Processing")
    print(f"Próba załadowania {num_rows:,} wierszy do pamięci i wykonania GROUP BY...")

    result_queue = mp.Queue()
    proc = mp.Process(target=_pandas_worker, args=(parquet_file.as_posix(), result_queue))
    peak_holder = []
    stop_event = threading.Event()

    start_time = time.time()
    proc.start()

    mon_thread = threading.Thread(target=memory_monitor, args=(proc.pid, stop_event, peak_holder))
    mon_thread.start()

    proc.join()
    stop_event.set()
    mon_thread.join()
    duration = time.time() - start_time

    res = result_queue.get() if not result_queue.empty() else {
        "success": False, "duration": duration, "error": "Proces zakończył się niespodziewanie (np. OOM Killer)"
    }

    if not res["success"]:
        print(f"   {RED}Błąd Pandas:{RESET} {res['error']}")
        return False, duration, 0

    peak_mb = (peak_holder[0] / (1024 * 1024)) if peak_holder else 0
    print(f"   {RED}{BOLD}🚨 Zużycie RAM przez proces Pandas: {peak_mb:.1f} MB!{RESET}")
    print(f"   ℹ️  Gdyby RAM był ograniczony do {memory_limit}, Pandas natychmiast zgłosiłby {RED}MemoryError{RESET}.")
    return True, res["duration"], peak_mb


def _duckdb_worker(parquet_file: str, temp_dir: Path, memory_limit: str, threads: int, result_queue: mp.Queue):
    """Kod DuckDB wykonywany w osobnym procesie OS z limitem pamięci i buforem dyskowym."""
    import time
    import duckdb

    try:
        con = duckdb.connect()
        con.execute(f"SET max_memory = '{memory_limit}';")
        con.execute(f"SET temp_directory = '{temp_dir.as_posix()}';")
        con.execute(f"SET threads = {threads};")

        t0 = time.time()
        print("   -> [DuckDB] Wykonywanie zapytania wprost na pliku Parquet...")
        query_explain = f"""
            EXPLAIN ANALYZE
            SELECT 
                category_id,
                COUNT(*) AS total_orders,
                ROUND(AVG(amount), 2) AS avg_amount,
                ROUND(SUM(amount), 2) AS total_revenue
            FROM '{parquet_file}'
            GROUP BY category_id
            ORDER BY total_revenue DESC
            LIMIT 5;
        """
        explain_rows = con.execute(query_explain).fetchall()
        explain_plan = explain_rows[0][1] if explain_rows else ""
        total_time = time.time() - t0

        spilled_mb = 0.0
        for line in explain_plan.splitlines():
            if "Data Written:" in line:
                val = line.split("Data Written:")[1].replace("│", "").strip()
                if "MB" in val:
                    try:
                        spilled_mb = float(val.replace("MB", "").strip())
                    except ValueError:
                        pass

        query_res = f"""
            SELECT 
                category_id,
                COUNT(*) AS total_orders,
                ROUND(AVG(amount), 2) AS avg_amount,
                ROUND(SUM(amount), 2) AS total_revenue
            FROM '{parquet_file}'
            GROUP BY category_id
            ORDER BY total_revenue DESC
            LIMIT 3;
        """
        df_res = con.execute(query_res).fetchdf()

        print(f"   -> [DuckDB] Zapytanie ukończone w {total_time:.2f}s!")
        print("   -> Top 3 wyniki:")
        for _, row in df_res.iterrows():
            print(f"      kat: {int(row['category_id'])} | zamówień: {int(row['total_orders'])} | suma: {row['total_revenue']:.2f}")

        result_queue.put({"success": True, "duration": total_time, "spilled_mb": spilled_mb, "error": None})
    except Exception as e:
        result_queue.put({"success": False, "duration": 0.0, "spilled_mb": 0.0, "error": str(e)})


def run_duckdb_test(parquet_file: Path, temp_dir: Path, memory_limit: str, threads: int = 4):
    """Uruchamia test w DuckDB ze ścisłym limitem max_memory i spillingiem na dysk."""
    print_header(f"2. DuckDB: Strumieniowanie + Spilling to disk (Limit: {memory_limit})")
    print(f"To samo zapytanie z limitem pamięci {BOLD}{memory_limit}{RESET} i katalogiem tymczasowym...")

    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    result_queue = mp.Queue()
    proc = mp.Process(target=_duckdb_worker, args=(parquet_file.as_posix(), temp_dir, memory_limit, threads, result_queue))
    peak_holder = []
    stop_event = threading.Event()

    start_time = time.time()
    proc.start()

    mon_thread = threading.Thread(target=memory_monitor, args=(proc.pid, stop_event, peak_holder))
    mon_thread.start()

    proc.join()
    stop_event.set()
    mon_thread.join()
    duration = time.time() - start_time

    res = result_queue.get() if not result_queue.empty() else {
        "success": False, "duration": duration, "spilled_mb": 0.0, "error": "Proces DuckDB zakończył się błędem"
    }

    if not res["success"]:
        print(f"   {RED}Błąd DuckDB:{RESET} {res['error']}")
        return False, duration, 0, 0

    peak_mb = (peak_holder[0] / (1024 * 1024)) if peak_holder else 0
    print(f"   {GREEN}{BOLD}✅ Szczytowe zużycie RAM przez proces DuckDB: {peak_mb:.1f} MB (w limicie {memory_limit})!{RESET}")
    if res["spilled_mb"] > 0:
        print(f"   {YELLOW}{BOLD}💾 Mechanizm Out-of-core w akcji: Data Written to disk = {res['spilled_mb']:.1f} MB{RESET}")

    return True, res["duration"], peak_mb, res["spilled_mb"]


def print_summary(pandas_res, duckdb_res):
    table = []
    if pandas_res is not None:
        p_ok, p_time, p_mem = pandas_res
        table.append([f"{RED}Pandas (In-Memory){RESET}", f"{p_mem:.1f} MB", f"{p_time:.2f} s"])
    if duckdb_res is not None:
        d_ok, d_time, d_mem, d_spill = duckdb_res
        table.append([f"{GREEN}DuckDB (Out-of-Core){RESET}", f"{d_mem:.1f} MB", f"{d_time:.2f} s"])

    headers = ["Silnik", "Szczytowy RAM", "Czas"]
    try:
        from tabulate import tabulate
        print("\n" + tabulate(table, headers=headers, tablefmt="rounded_grid") + "\n")
    except ImportError:
        header_line = f"{'Silnik':<25} | {'Szczytowy RAM':<15} | {'Czas':<10}"
        print("\n" + header_line)
        print("-" * len(header_line))
        for row in table:
            print(f"{row[0]:<35} | {row[1]:<15} | {row[2]:<10}")
        print("\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Demonstracja na żywo: Zarządzanie pamięcią (Out-of-core) w DuckDB vs Pandas",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-r", "--rows",
        type=int,
        default=400_000_000,
        help="Liczba wierszy w generowanym zbiorze Parquet"
    )
    parser.add_argument(
        "-m", "--memory-limit",
        type=str,
        default="1G",
        help="Limit pamięci RAM dla DuckDB (np. 64MB, 128MB, 512MB, 1GB, 2GB)"
    )
    parser.add_argument(
        "-f", "--file",
        type=Path,
        default=Path("duze_zamowienia.parquet"),
        help="Ścieżka do pliku Parquet z danymi testowymi"
    )
    parser.add_argument(
        "-t", "--temp-dir",
        type=Path,
        default=Path("./duckdb_temp_spill"),
        help="Ścieżka do katalogu na pliki tymczasowe zrzucane na dysk (spill)"
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=4,
        help="Liczba wątków roboczych DuckDB"
    )
    parser.add_argument(
        "--skip-pandas",
        action="store_true",
        help="Pomiń test Pandas (uruchom wyłącznie test DuckDB)"
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Wymuś wygenerowanie pliku Parquet na nowo"
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Nie usuwaj katalogu tymczasowego po zakończeniu testu"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print_header("ZARZĄDZANIE PAMIĘCIĄ (OUT-OF-CORE) W DUCKDB")
    print("Konfiguracja parametrów CLI:")
    print(f"  • Plik danych:       {args.file} ({args.rows:,} wierszy)")
    print(f"  • Limit pamięci RAM: {args.memory_limit}")
    print(f"  • Liczba wątków:     {args.threads}")
    print(f"  • Bufor dyskowy:     {args.temp_dir}")

    ensure_dataset(args.file, args.rows, force=args.regenerate)

    pandas_res = None
    if not args.skip_pandas:
        pandas_res = run_pandas_test(args.file, args.rows, args.memory_limit)

    duckdb_res = run_duckdb_test(args.file, args.temp_dir, args.memory_limit, args.threads)

    print_summary(pandas_res, duckdb_res)

    if not args.keep_temp and args.temp_dir.exists():
        shutil.rmtree(args.temp_dir)


if __name__ == "__main__":
    main()
