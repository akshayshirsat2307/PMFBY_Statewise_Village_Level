name: PMFBY Weekly Scrape Save to data and Commit

on:
  schedule:
    - cron: '0 9 * * 1'   # Every Monday at 09:00 UTC
  workflow_dispatch:

permissions:
  contents: write

jobs:
  scrape-and-commit:
    runs-on: ubuntu-latest
    timeout-minutes: 60

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install browser and Python dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y chromium chromium-driver
          which chromium
          which chromedriver
          chromium --version
          chromedriver --version

          python -m pip install --upgrade pip
          python -m pip install beautifulsoup4 selenium

      - name: Run PMFBY scraper
        run: |
          python pmfby_scraper_dashboard.py \
            --year 2026 \
            --season Kharif \
            --scheme BOTH \
            --drill-to-district \
            --retries 3

      - name: Commit CSV files in data folder
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "41898282+github-actions[bot]@users.noreply.github.com"

          git add data/*.csv

          if git diff --cached --quiet; then
            echo "No new data files to commit."
            exit 0
          fi

          git commit -m "Weekly PMFBY data update $(date -u +'%Y-%m-%d')"
          git push
