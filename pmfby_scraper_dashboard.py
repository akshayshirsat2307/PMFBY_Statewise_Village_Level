
#### This code working fine for downloading district level data from PMFBY dashboard: https://pmfby.gov.in/adminStatistics/dashboard

# # auto-named: pmfby_ANDHRA_PRADESH_2025_Kharif_PMFBY.csv
# python .\PMFBY_Dashboard_State_Data_Download_V4.py --year 2025 --season Kharif --scheme PMFBY --state "ANDHRA PRADESH"

# # auto-named per state: pmfby_<STATE>_2025_Kharif_PMFBY.csv for every state
# python .\PMFBY_Dashboard_State_Data_Download_V4.py --year 2025 --season Kharif --scheme PMFBY --drill-to-district

# # force everything into one shared file instead--- not worling properly sometimes
# python .\PMFBY_Dashboard_State_Data_Download_V4.py --year 2025 --season Kharif --scheme PMFBY --drill-to-district --output all_states.csv

# python .\PMFBY_Dashboard_State_Data_Download_V5.py --year 2025 --season Kharif --scheme BOTH --drill-to-district --output all_states.csv


# Working fine for both PMFBY and WBCIS schemes, and also for BOTH schemes together.


import argparse
import csv
import os
import re
import time
from dataclasses import dataclass
from typing import List, Optional

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

DASHBOARD_URL = "https://pmfby.gov.in/adminStatistics/dashboard"
dt = time.strftime("%Y%m%d_%H%M%S")
MASTER_CSV = f"pmfby_district_data{dt}.csv"
WAIT_SECONDS = 20

SELECTORS = {
    "state_wise_report_link": '//a[@title="State Wise Report"]',
    "year_dropdown": '//label[normalize-space()="Year"]/following-sibling::select',
    "season_dropdown": '//label[normalize-space()="Season"]/following-sibling::select',
    "scheme_dropdown": '//label[normalize-space()="Scheme"]/following-sibling::select',
    "row_link_by_title": 'a[title="{name}"]',
    "results_table": "table.adminStatics__dashboardTableDT___1cEkH",
    "results_count_text": "p.adminStatics__resultText___2ilrx",
}

SEASON_CODES = {"Kharif": "01", "Rabi": "02"}
SCHEME_CODES = {"PMFBY": "04", "WBCIS": "02"}


@dataclass
class FilterSpec:
    year: str
    season: str
    scheme: str
    state: Optional[str] = None


def sanitize_filename_part(text: str) -> str:
    text = text.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9_-]", "", text)


def build_csv_filename(spec: FilterSpec, district: Optional[str] = None) -> str:
    parts = ["pmfby"]
    if spec.state:
        parts.append(sanitize_filename_part(spec.state))
    if district:
        parts.append(sanitize_filename_part(district))
    parts.extend([
        sanitize_filename_part(spec.year),
        sanitize_filename_part(spec.season),
        sanitize_filename_part(spec.scheme),
    ])
    return "_".join(parts) + ".csv"


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


def select_dropdown_by_value(driver, selector, value):
    el = wait_visible(driver, selector)
    Select(el).select_by_value(value)
    time.sleep(1.5)


def click_row_link_by_title(driver, name):

    el = WebDriverWait(driver, WAIT_SECONDS).until(
        lambda d: d.execute_script(
            """
            const table = document.querySelector(
                'table.adminStatics__dashboardTableDT___1cEkH'
            );

            if (!table) return null;

            return Array.from(
                table.querySelectorAll('tbody a[title]')
            ).find(
                a => (a.getAttribute('title') || '').trim() === arguments[0]
            ) || null;
            """,
            name,
        )
    )

    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});",
        el
    )

    try:
        el.click()
    except Exception:
        driver.execute_script(
            "arguments[0].click();",
            el
        )

    time.sleep(1.5)


def navigate_to(driver, spec: FilterSpec):
    driver.get(DASHBOARD_URL)
    WebDriverWait(driver, WAIT_SECONDS).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

    wait_clickable(driver, SELECTORS["state_wise_report_link"]).click()
    time.sleep(2)

    select_dropdown_by_value(driver, SELECTORS["year_dropdown"], spec.year)
    select_dropdown_by_value(
        driver, SELECTORS["season_dropdown"], SEASON_CODES[spec.season]
    )
    select_dropdown_by_value(
        driver, SELECTORS["scheme_dropdown"], SCHEME_CODES[spec.scheme]
    )

    if spec.state:
        click_row_link_by_title(driver, spec.state)


def extract_table_rows(driver):
    try:
        wait_visible(driver, SELECTORS["results_table"])
    except TimeoutException:
        return [], []

    time.sleep(1)
    table_el = driver.find_element(By.CSS_SELECTOR, SELECTORS["results_table"])
    soup = BeautifulSoup(table_el.get_attribute("outerHTML"), "html.parser")
    headers = [th.get_text(" ", strip=True) for th in soup.select("thead th")]

    tbody = soup.find("tbody")
    if not tbody:
        return headers, []

    rows = []
    for tr in tbody.find_all("tr"):
        vals = []
        for td in tr.find_all("td"):
            anchor = td.find("a")
            vals.append(anchor.get("title") if anchor and anchor.get("title") else td.get_text(" ", strip=True))
        if vals:
            rows.append(vals)
    return headers, rows


def row_names(driver) -> List[str]:
    """
    Return only real clickable state names from the results table.

    This prevents total/count values such as 60, 41, 467, 151, etc.
    from being incorrectly treated as state names.
    """

    wait_visible(driver, SELECTORS["results_table"])

    table = driver.find_element(
        By.CSS_SELECTOR,
        SELECTORS["results_table"]
    )

    links = table.find_elements(
        By.CSS_SELECTOR,
        "tbody a[title]"
    )

    states = []

    for link in links:
        name = (link.get_attribute("title") or "").strip()

        # Keep only values containing alphabetic characters.
        # This removes numeric totals such as 60 and 41.
        if name and any(char.isalpha() for char in name):

            if name not in states:
                states.append(name)

    return states

def drop_grand_total(headers, rows):
    # Robust against merged headers and dashboard variations.
    filtered = [
        row for row in rows
        if not any(str(cell).strip().lower() == "grand total" for cell in row)
    ]
    return headers, filtered


def append_rows(spec: FilterSpec, headers: List[str], rows: List[List[str]], csv_path=MASTER_CSV):
    if not rows:
        return

    meta_cols = ["Year", "Season", "Scheme", "State (selected)"]
    meta_vals = [spec.year, spec.season, spec.scheme, spec.state or ""]
    max_cols = max(len(row) for row in rows)

    # Merged dashboard headers often do not equal the actual data-column count.
    data_headers = headers if len(headers) == max_cols else [f"Col{i + 1}" for i in range(max_cols)]

    file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0
    with open(csv_path, "a", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(meta_cols + data_headers)
        for row in rows:
            writer.writerow(meta_vals + row + [""] * (max_cols - len(row)))


def run_single_scheme_job(
    driver,
    spec: FilterSpec,
    drill_to_district: bool = False,
    csv_path: Optional[str] = None,
):
    if not drill_to_district:
        navigate_to(driver, spec)
        headers, rows = extract_table_rows(driver)
        headers, rows = drop_grand_total(headers, rows)
        out_path = csv_path or build_csv_filename(spec)
        append_rows(spec, headers, rows, csv_path=out_path)
        label = spec.state or "(state-level summary)"
        print(f"Saved {len(rows)} rows for {label}, {spec.scheme} -> {out_path}")
        return

    base_spec = FilterSpec(spec.year, spec.season, spec.scheme, None)
    navigate_to(driver, base_spec)
    states = row_names(driver)
    print(f"[{spec.scheme}] Found {len(states)} states")

    for state in states:
        try:
            state_spec = FilterSpec(spec.year, spec.season, spec.scheme, state)
            navigate_to(driver, state_spec)
            headers, rows = extract_table_rows(driver)
            headers, rows = drop_grand_total(headers, rows)
            out_path = csv_path or build_csv_filename(state_spec)
            append_rows(state_spec, headers, rows, csv_path=out_path)
            print(f"  [{spec.scheme}] Saved {state}: {len(rows)} district rows -> {out_path}")
        except Exception as exc:
            print(f"  [{spec.scheme}] FAILED {state}: {exc}")


def normalize_schemes(raw_scheme: str) -> List[str]:
    value = raw_scheme.strip().upper().replace(" ", "")
    if value in {"BOTH", "ALL", "PMFBY&WBCIS", "WBCIS&PMFBY", "PMFBY+WBCIS", "WBCIS+PMFBY"}:
        return ["PMFBY", "WBCIS"]
    if value in SCHEME_CODES:
        return [value]
    raise argparse.ArgumentTypeError(
        "--scheme must be PMFBY, WBCIS, BOTH, or PMFBY&WBCIS"
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Scrape PMFBY admin statistics dashboard at state/district level"
    )
    parser.add_argument("--year", required=True, help="Example: 2025")
    parser.add_argument("--season", required=True, choices=["Kharif", "Rabi"])
    parser.add_argument(
        "--scheme",
        required=True,
        help='PMFBY, WBCIS, BOTH, or "PMFBY&WBCIS"',
    )
    parser.add_argument("--state", default=None, help='Example: "ANDHRA PRADESH"')
    parser.add_argument(
        "--drill-to-district",
        action="store_true",
        help="Loop through every state and save district-level tables",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Shared CSV output. When omitted, one file is generated per state and scheme",
    )
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    schemes = normalize_schemes(args.scheme)

    if args.drill_to_district and args.state:
        print("Note: --state is ignored because --drill-to-district was supplied.")

    driver = make_driver(headless=not args.headed)
    try:
        for scheme in schemes:
            print(f"\nStarting scheme: {scheme}")
            spec = FilterSpec(
                year=args.year,
                season=args.season,
                scheme=scheme,
                state=None if args.drill_to_district else args.state,
            )
            run_single_scheme_job(
                driver,
                spec,
                drill_to_district=args.drill_to_district,
                csv_path=args.output,
            )
    finally:
        driver.quit()

    print("Done.")
