
#### This code working fine for downloading district level data from PMFBY dashboard: https://pmfby.gov.in/adminStatistics/dashboard

# # auto-named: pmfby_ANDHRA_PRADESH_2025_Kharif_PMFBY.csv
# python .\PMFBY_Dashboard_State_Data_Download_v2.py --year 2025 --season Kharif --scheme PMFBY --state "ANDHRA PRADESH"

# # auto-named per state: pmfby_<STATE>_2025_Kharif_PMFBY.csv for every state
# python .\PMFBY_Dashboard_State_Data_Download_v2.py --year 2025 --season Kharif --scheme PMFBY --drill-to-district

# # force everything into one shared file instead--- not worling properly sometimes
# python .\PMFBY_Dashboard_State_Data_Download_v2.py --year 2025 --season Kharif --scheme PMFBY --drill-to-district --output all_states.csv



import csv
import os
import time
from dataclasses import dataclass
from typing import Optional, List

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

DASHBOARD_URL = "https://pmfby.gov.in/adminStatistics/dashboard"
DOWNLOAD_DIR = "download_dashboard"  # Directory to save CSV files
# MASTER_CSV = "pmfby_district_data_28Sept26.csv"  # fallback name if no spec-based name applies


def ensure_download_dir():
    """Ensure the download directory exists."""
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)


def sanitize_filename_part(text: str) -> str:
    """Make a string safe to use inside a filename (spaces -> underscores,
    strip anything that isn't alnum/underscore/hyphen)."""
    import re
    text = text.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9_\-]", "", text)


def build_csv_filename(spec, district: Optional[str] = None) -> str:
    """Builds a filename like:
         pmfby_ANDHRA_PRADESH_2025_Kharif_PMFBY.csv
    or, if a single district is also known:
         pmfby_ANDHRA_PRADESH_GUNTUR_2025_Kharif_PMFBY.csv
    Falls back to a state-less name (state-level summary run) like:
         pmfby_2025_Kharif_PMFBY.csv
    Returns the path with download_dashboard directory prefix.
    """
    parts = ["pmfby"]
    if spec.state:
        parts.append(sanitize_filename_part(spec.state))
    if district:
        parts.append(sanitize_filename_part(district))
    parts += [
        sanitize_filename_part(spec.year),
        sanitize_filename_part(spec.season),
        sanitize_filename_part(spec.scheme),
    ]
    filename = "_".join(parts) + ".csv"
    return os.path.join(DOWNLOAD_DIR, filename)

# ---------------------------------------------------------------------------
# SELECTORS — confirmed against real page HTML (debug_page_after_click.html)
# ---------------------------------------------------------------------------
SELECTORS = {
    # The "State Wise Report" link is a client-side React state toggle, not
    # a real navigation (href points at the same URL). Must click it before
    # any of the Year/Season/Scheme selects exist in the DOM.
    "state_wise_report_link": '//a[@title="State Wise Report"]',

    # Confirmed real <select class="form-control"> elements, each preceded
    # by a sibling <label>. These only appear AFTER state_wise_report_link
    # has been clicked.
    "year_dropdown": '//label[normalize-space()="Year"]/following-sibling::select',
    "season_dropdown": '//label[normalize-space()="Season"]/following-sibling::select',
    "scheme_dropdown": '//label[normalize-space()="Scheme"]/following-sibling::select',

    # There is NO State or District <select>. States are rows in the results
    # table; each state name is a clickable <a title="STATE NAME"> with no
    # href (JS onClick). Clicking one swaps the table to that state's
    # districts — already the granularity we want, no further click needed.
    "row_link_by_title": 'a[title="{name}"]',

    "results_table": "table.adminStatics__dashboardTableDT___1cEkH",
    "results_count_text": "p.adminStatics__resultText___2ilrx",  # "Showing Result: N"
}

# Season and Scheme dropdowns use coded <option value="..">, not their
# visible label — confirmed from the copied HTML.
SEASON_CODES = {"Kharif": "01", "Rabi": "02"}
SCHEME_CODES = {"PMFBY": "04", "WBCIS": "02"}

WAIT_SECONDS = 20


@dataclass
class FilterSpec:
    year: str
    season: str          # "Kharif" or "Rabi"
    scheme: str           # "PMFBY" or "WBCIS"
    state: Optional[str] = None   # None = scrape the state-level summary table


# ---------------------------------------------------------------------------
# Browser setup
# ---------------------------------------------------------------------------
def make_driver(headless: bool = True):
    from selenium.webdriver.chrome.options import Options
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,1000")
    driver = webdriver.Chrome(options=opts)
    driver.implicitly_wait(3)
    return driver


def _is_xpath(selector: str) -> bool:
    return selector.startswith("//") or selector.startswith("(")


def wait_visible(driver, selector, timeout=WAIT_SECONDS):
    by = By.XPATH if _is_xpath(selector) else By.CSS_SELECTOR
    return WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((by, selector))
    )


def wait_clickable(driver, selector, timeout=WAIT_SECONDS):
    by = By.XPATH if _is_xpath(selector) else By.CSS_SELECTOR
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, selector))
    )


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
def select_dropdown_by_value(driver, selector, value):
    el = wait_visible(driver, selector)
    Select(el).select_by_value(value)
    time.sleep(1.5)  # allow the table to refresh after the filter change


def click_row_link_by_title(driver, name):
    css = SELECTORS["row_link_by_title"].format(name=name)
    el = wait_clickable(driver, css)
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    try:
        el.click()
    except Exception:
        driver.execute_script("arguments[0].click();", el)
    time.sleep(1.5)


def navigate_to(driver, spec: FilterSpec):
    driver.get(DASHBOARD_URL)
    WebDriverWait(driver, WAIT_SECONDS).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

    # Must click this BEFORE the Year/Season/Scheme selects exist in the DOM.
    report_link = wait_clickable(driver, SELECTORS["state_wise_report_link"])
    report_link.click()
    time.sleep(2)

    select_dropdown_by_value(driver, SELECTORS["year_dropdown"], spec.year)
    select_dropdown_by_value(
        driver, SELECTORS["season_dropdown"], SEASON_CODES[spec.season]
    )
    select_dropdown_by_value(
        driver, SELECTORS["scheme_dropdown"], SCHEME_CODES[spec.scheme]
    )

    if spec.state:
        # Clicking the state name swaps the table from "all states" to
        # "all districts within this state" — this IS the district-level
        # data, no further click required.
        click_row_link_by_title(driver, spec.state)


# ---------------------------------------------------------------------------
# Table extraction
# ---------------------------------------------------------------------------
def get_results_count(driver) -> Optional[str]:
    try:
        el = driver.find_element(By.CSS_SELECTOR, SELECTORS["results_count_text"])
        return el.text.strip()
    except NoSuchElementException:
        return None


def extract_table_rows(driver):
    try:
        wait_visible(driver, SELECTORS["results_table"])
    except TimeoutException:
        print("[WARNING] Table not found within timeout. Check selectors or page load.")
        return [], []

    time.sleep(1)
    table_el = driver.find_element(By.CSS_SELECTOR, SELECTORS["results_table"])
    html = table_el.get_attribute("outerHTML")
    soup = BeautifulSoup(html, "html.parser")

    # Column headers — dashboard has a two-row <thead> with rowspan/colspan,
    # so just grab all <th> text in document order as a best-effort header
    # list (used for reference; CSV writer below uses positional data).
    headers = [th.get_text(strip=True) for th in soup.select("thead th")]

    tbody = soup.find("tbody")
    if not tbody:
        print("[WARNING] No tbody found in table. Table may be empty or structure has changed.")
        return headers, []

    rows = []
    for tr in tbody.find_all("tr"):
        vals = []
        for td in tr.find_all("td"):
            a = td.find("a")
            vals.append(a.get("title") if a else td.get_text(strip=True))
        rows.append(vals)
    return headers, rows


def row_names(driver) -> List[str]:
    """Names (2nd column) of every row in the currently visible table —
    used to enumerate every state to loop into."""
    _, rows = extract_table_rows(driver)
    return [r[1] for r in rows if len(r) > 1 and r[1]]


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------
def append_rows(spec: FilterSpec, headers: List[str], rows: List[List[str]], csv_path: str):
    """
    Append rows to a CSV file.
    
    Args:
        spec: FilterSpec with year, season, scheme, state
        headers: Column headers from the table
        rows: Data rows to append
        csv_path: Full path to the CSV file (required - no default)
    """
    meta_cols = ["Year", "Season", "Scheme", "State (selected)"]
    meta_vals = [spec.year, spec.season, spec.scheme, spec.state or ""]

    file_exists = os.path.exists(csv_path)
    
    # Validation: check if we have data to write
    if not rows:
        print(f"[WARNING] No rows to write to {csv_path}")
        return
    
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            # Fall back to generic numbered columns if header count doesn't
            # line up with actual row length (merged/rowspan headers can
            # cause this on complex dashboard tables).
            data_headers = headers if headers else [f"Col{i}" for i in range(len(rows[0]) if rows else 0)]
            writer.writerow(meta_cols + data_headers)
        for r in rows:
            writer.writerow(meta_vals + r)


# ---------------------------------------------------------------------------
# High-level job runner
# ---------------------------------------------------------------------------
def run_job(driver, spec: FilterSpec, drill_to_district: bool = False, csv_path: Optional[str] = None):
    """
    csv_path=None (default): auto-name the CSV per run from spec fields —
        pmfby_<STATE>_<YEAR>_<SEASON>_<SCHEME>.csv (saved to download_dashboard folder)
    csv_path="some_file.csv": use that exact name/path for every write
        instead (all states appended into one shared file when combined
        with --drill-to-district).

    drill_to_district=False:
        - if spec.state is None: scrape the state-level summary table (one
          row per state).
        - if spec.state is set: scrape that one state's district-level table.

    drill_to_district=True:
        - spec.state should be None. Loads the state-level table, gets every
          state name, then re-navigates into each one and saves its
          district-level table (one CSV per state, auto-named, unless
          csv_path was explicitly given).
    """
    ensure_download_dir()
    
    if not drill_to_district:
        navigate_to(driver, spec)
        headers, rows = extract_table_rows(driver)
        
        if not rows:
            print(f"[ERROR] No data extracted for {spec.state or '(state-level summary)'}. Skipping.")
            return
        
        out_path = build_csv_filename(spec)
        append_rows(spec, headers, rows, csv_path=out_path)
        label = spec.state or "(state-level summary)"
        print(f"✓ Saved {len(rows)} rows for {label} -> {out_path}")
        return

    base_spec = FilterSpec(year=spec.year, season=spec.season, scheme=spec.scheme, state=None)
    navigate_to(driver, base_spec)
    state_names = row_names(driver)
    print(f"Found {len(state_names)} states")

    if not state_names:
        print("[ERROR] No states found. Check page selectors or network connectivity.")
        return

    for state in state_names:
        state_spec = FilterSpec(year=spec.year, season=spec.season, scheme=spec.scheme, state=state)
        navigate_to(driver, state_spec)
        headers, rows = extract_table_rows(driver)
        
        if not rows:
            print(f"  [SKIP] {state}: No data extracted")
            continue
        
        out_path = build_csv_filename(state_spec)
        append_rows(state_spec, headers, rows, csv_path=out_path)
        print(f"  ✓ {state}: {len(rows)} district rows -> {out_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args():
    import argparse

    p = argparse.ArgumentParser(description="Scrape PMFBY admin statistics dashboard (State/District level)")
    p.add_argument("--year", required=True, help="e.g. 2025")
    p.add_argument("--season", required=True, choices=["Kharif", "Rabi"])
    p.add_argument("--scheme", required=True, choices=["PMFBY", "WBCIS"])
    p.add_argument("--state", default=None, help="e.g. 'ANDHRA PRADESH' (omit for the state-level summary, or use --drill-to-district for all states)")
    p.add_argument(
        "--drill-to-district",
        action="store_true",
        help="Ignore --state; loop through every state and save its district-level table.",
    )
    p.add_argument(
        "--output",
        default=None,
        help="CSV path to write to. If omitted, auto-generates a name like "
             "pmfby_<STATE>_<YEAR>_<SEASON>_<SCHEME>.csv per state in the download_dashboard folder.",
    )
    p.add_argument(
        "--headed",
        action="store_true",
        help="Run with a visible browser window (debugging only).",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    spec = FilterSpec(
        year=args.year,
        season=args.season,
        scheme=args.scheme,
        state=args.state,
    )

    driver = make_driver(headless=not args.headed)
    try:
        run_job(driver, spec, drill_to_district=args.drill_to_district, csv_path=args.output)
    finally:
        driver.quit()

    print("Done.")
