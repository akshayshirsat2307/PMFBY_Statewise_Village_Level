"""
PMFBY Admin Statistics Dashboard Scraper
=========================================
Scrapes https://pmfby.gov.in/adminStatistics/dashboard with configurable
filters: Year, Season, Scheme, State, District, Mandal, Grampanchayat, Village.

REQUIREMENTS (run this on a machine with internet access — NOT in a
sandboxed/offline environment):
    pip install selenium beautifulsoup4 pandas webdriver-manager

WHY SELENIUM, NOT requests/BeautifulSoup ALONE:
    The dashboard is a JavaScript-rendered SPA. Filters are dropdowns that
    trigger API calls behind the scenes; plain requests.get() only returns
    an empty HTML shell. Selenium drives a real browser so the JS executes
    and dropdown state changes we click actually populate the tables.

IMPORTANT — SELECTOR PLACEHOLDERS:
    I do not have live access to the site's DOM (no browser/network tool in
    my sandbox), so the CSS/XPath selectors below are best-guess placeholders
    based on the table structure you've pasted. Before running at scale:
      1. Open the dashboard in Chrome, right-click each dropdown -> Inspect.
      2. Replace the SELECTORS dict values below with the real element
         id/name/class you see in DevTools.
      3. Test on ONE filter combination first (state-level only) before
         looping over hundreds of Mandal/GP/Village combinations.

USAGE:
    python pmfby_scraper.py

    Edit the JOBS list at the bottom to control what gets scraped.
"""

import csv
import os
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

DASHBOARD_URL = "https://pmfby.gov.in/adminStatistics/dashboard"
MASTER_CSV = "pmfby_district_data.csv"

# ---------------------------------------------------------------------------
# 1. SELECTOR PLACEHOLDERS — replace with real values from DevTools inspection
# ---------------------------------------------------------------------------
SELECTORS = {
    # Confirmed from copied HTML: dropdowns have no id/name, only
    # class="form-control". They're distinguished by the <label> text that
    # precedes them, so we locate them via XPath off the label.
    "year_dropdown": '//label[normalize-space()="Year"]/following-sibling::select',
    "season_dropdown": '//label[normalize-space()="Season"]/following-sibling::select',
    "scheme_dropdown": '//label[normalize-space()="Scheme"]/following-sibling::select',
    # NOT YET CONFIRMED — State/District dropdowns and the drill-down links
    # (Mandal/GP/Village) haven't been inspected yet. Update these once you
    # copy those elements the same way you did for Year/Season/Scheme.
    "state_dropdown": '//label[normalize-space()="State"]/following-sibling::select',
    "district_dropdown": '//label[normalize-space()="District"]/following-sibling::select',
    "mandal_link_by_title": 'a[title="{name}"]', # mandal names are <a title="...">
    "gp_link_by_title": 'a[title="{name}"]',     # same pattern one level down
    "village_link_by_title": 'a[title="{name}"]',
    "submit_button": "button#submit",            # if a "Go/Submit" button exists
    "results_table": "table.adminStatics__dashboardTableDT___1cEkH",
    "results_count_text": "p.adminStatics__resultText___2ilrx",  # "Showing Result: N"
}

# Season and Scheme dropdowns use coded <option value="..">, not their
# visible label — confirmed from the copied HTML.
SEASON_CODES = {"Kharif": "01", "Rabi": "02"}
SCHEME_CODES = {"PMFBY": "04", "WBCIS": "02"}

WAIT_SECONDS = 15


@dataclass
class FilterSpec:
    year: str
    season: str          # "Kharif" or "Rabi"
    scheme: str           # "PMFBY" or "WBCIS"
    state: str
    district: Optional[str] = None
    mandal: Optional[str] = None
    grampanchayat: Optional[str] = None
    village: Optional[str] = None


# ---------------------------------------------------------------------------
# 2. Browser setup
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
# 3. Drill-down navigation
# ---------------------------------------------------------------------------
def select_dropdown_by_text(driver, selector, visible_text):
    el = wait_visible(driver, selector)
    Select(el).select_by_visible_text(visible_text)
    time.sleep(1)  # allow dependent dropdowns / API calls to refresh


def select_dropdown_by_value(driver, selector, value):
    el = wait_visible(driver, selector)
    Select(el).select_by_value(value)
    time.sleep(1)


def click_link_by_title(driver, css_selector_template, name):
    css = css_selector_template.format(name=name)
    el = wait_clickable(driver, css)
    el.click()
    time.sleep(1.5)


def navigate_to(driver, spec: FilterSpec):
    driver.get(DASHBOARD_URL)

    # Year: <option value="2025">2025</option> — value == visible text
    select_dropdown_by_value(driver, SELECTORS["year_dropdown"], spec.year)

    # Season/Scheme: coded values, NOT their visible text
    select_dropdown_by_value(
        driver, SELECTORS["season_dropdown"], SEASON_CODES[spec.season]
    )
    select_dropdown_by_value(
        driver, SELECTORS["scheme_dropdown"], SCHEME_CODES[spec.scheme]
    )

    # NOT YET CONFIRMED: State dropdown — assuming visible-text options like
    # Year, but this needs verifying against the real element (it may also
    # use coded state IDs like Season/Scheme do).
    select_dropdown_by_text(driver, SELECTORS["state_dropdown"], spec.state)

    if spec.district:
        select_dropdown_by_text(driver, SELECTORS["district_dropdown"], spec.district)

    if spec.mandal:
        click_link_by_title(driver, SELECTORS["mandal_link_by_title"], spec.mandal)

    if spec.grampanchayat:
        click_link_by_title(driver, SELECTORS["gp_link_by_title"], spec.grampanchayat)

    if spec.village:
        click_link_by_title(driver, SELECTORS["village_link_by_title"], spec.village)


# ---------------------------------------------------------------------------
# 4. Table extraction (same parsing logic used for pasted tables)
# ---------------------------------------------------------------------------
GENERIC_HEADERS = [
    "S. No", "Name", "Insurance Units", "Farmers", "Loanee", "Non-Loanee",
    "Area Insured", "Farmers Premium", "State Premium", "GOI Premium",
    "Gross Premium", "Sum Insured", "Male", "Female", "Gender Others",
    "SC", "ST", "OBC", "GEN", "Marginal", "Small", "Farmer Type Others",
    "Prevented Sowing", "Localized", "Mid-term", "Yield Based",
    "Post Harvest", "WBCIS", "Total Claim Paid",
]


def get_results_count(driver) -> Optional[str]:
    """Reads the 'Showing Result: N' text — useful to confirm a filter
    change actually took effect before trusting the table content."""
    try:
        el = driver.find_element(By.CSS_SELECTOR, SELECTORS["results_count_text"])
        return el.text.strip()
    except NoSuchElementException:
        return None


def extract_table_rows(driver) -> List[List[str]]:
    try:
        wait_visible(driver, SELECTORS["results_table"])
    except TimeoutException:
        return []

    html = driver.find_element(By.CSS_SELECTOR, SELECTORS["results_table"]).get_attribute("outerHTML")
    soup = BeautifulSoup(html, "html.parser")
    tbody = soup.find("tbody")
    if not tbody:
        return []

    rows = []
    for tr in tbody.find_all("tr"):
        vals = []
        for td in tr.find_all("td"):
            a = td.find("a")
            vals.append(a.get("title") if a else td.get_text(strip=True))
        rows.append(vals)
    return rows


def row_names(driver) -> List[str]:
    """Grab just the clickable names (Mandal/GP/Village) in the current table,
    used to loop into every child of the current level."""
    rows = extract_table_rows(driver)
    return [r[1] for r in rows if len(r) > 1 and r[1]]


# ---------------------------------------------------------------------------
# 5. CSV writer (matches the schema we've been building manually)
# ---------------------------------------------------------------------------
def append_rows(spec: FilterSpec, rows: List[List[str]], csv_path=MASTER_CSV):
    meta_cols = ["Year", "Season", "State", "District", "Grampanchayat",
                 "Village", "Scheme"]
    meta_vals = [spec.year, spec.season, spec.state, spec.district or "",
                 spec.grampanchayat or "", spec.village or "", spec.scheme]

    file_exists = os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(meta_cols + ["Mandal Name"] + GENERIC_HEADERS[2:])
        for r in rows:
            writer.writerow(meta_vals + r)


# ---------------------------------------------------------------------------
# 6. High-level job runner
# ---------------------------------------------------------------------------
def run_job(driver, spec: FilterSpec, drill_to_village: bool = False, csv_path=MASTER_CSV):
    """
    If drill_to_village is False: just scrape whatever level `spec` points to
    (state summary, or district/mandal table) and save it.

    If True: spec must include state+district+mandal at minimum; this will
    walk every Grampanchayat under that Mandal, and every Village under each
    GP, saving village-level rows for the whole Mandal.
    """
    navigate_to(driver, spec)

    if not drill_to_village:
        rows = extract_table_rows(driver)
        append_rows(spec, rows, csv_path=csv_path)
        print(f"Saved {len(rows)} rows for {spec}")
        return

    # Drill Mandal -> GP -> Village
    navigate_to(driver, spec)  # lands on GP-list table for this Mandal
    gp_names = row_names(driver)
    print(f"Found {len(gp_names)} Grampanchayats under {spec.mandal}")

    for gp in gp_names:
        gp_spec = FilterSpec(**{**spec.__dict__, "grampanchayat": gp})
        navigate_to(driver, gp_spec)
        village_names = row_names(driver)
        print(f"  {gp}: {len(village_names)} villages")

        for village in village_names:
            v_spec = FilterSpec(**{**gp_spec.__dict__, "village": village})
            navigate_to(driver, v_spec)
            rows = extract_table_rows(driver)
            append_rows(v_spec, rows, csv_path=csv_path)
            print(f"    Saved {village}: {len(rows)} rows")


# ---------------------------------------------------------------------------
# 7. CLI — lets GitHub Actions (or you, locally) pass filters as arguments
# ---------------------------------------------------------------------------
def parse_args():
    import argparse

    p = argparse.ArgumentParser(description="Scrape PMFBY admin statistics dashboard")
    p.add_argument("--year", required=True, help="e.g. 2025")
    p.add_argument("--season", required=True, choices=["Kharif", "Rabi"])
    p.add_argument("--scheme", required=True, choices=["PMFBY", "WBCIS"])
    p.add_argument("--state", required=True, help="e.g. 'Andhra Pradesh'")
    p.add_argument("--district", default=None, help="optional; e.g. 'Pune'")
    p.add_argument("--mandal", default=None, help="optional; e.g. 'Junnar'")
    p.add_argument("--grampanchayat", default=None, help="optional; e.g. 'Otur'")
    p.add_argument("--village", default=None, help="optional; e.g. 'Otur'")
    p.add_argument(
        "--drill-to-village",
        action="store_true",
        help="If set (with --mandal given), walk every GP and village under "
             "that mandal automatically instead of just scraping one level.",
    )
    p.add_argument(
        "--output",
        default=MASTER_CSV,
        help=f"CSV path to append results to (default: {MASTER_CSV})",
    )
    p.add_argument(
        "--headed",
        action="store_true",
        help="Run with a visible browser window (debugging only; GH Actions "
             "should always run headless).",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    spec = FilterSpec(
        year=args.year,
        season=args.season,
        scheme=args.scheme,
        state=args.state,
        district=args.district,
        mandal=args.mandal,
        grampanchayat=args.grampanchayat,
        village=args.village,
    )

    driver = make_driver(headless=not args.headed)
    try:
        run_job(driver, spec, drill_to_village=args.drill_to_village, csv_path=args.output)
    finally:
        driver.quit()

    print(f"Done. Output: {args.output}")


# ---------------------------------------------------------------------------
# EXAMPLES (run locally):
#   python pmfby_scraper.py --year 2025 --season Kharif --scheme PMFBY \
#       --state "Andhra Pradesh" --district "Alluri Sitharama Raju" \
#       --mandal "Chintapalle" --drill-to-village
#
#   python pmfby_scraper.py --year 2025 --season Kharif --scheme PMFBY \
#       --state "Maharashtra" --district "Pune" --mandal "Junnar" \
#       --grampanchayat "Otur" --village "Otur"
#
#   python pmfby_scraper.py --year 2025 --season Kharif --scheme PMFBY \
#       --state "Karnataka"
# ---------------------------------------------------------------------------
