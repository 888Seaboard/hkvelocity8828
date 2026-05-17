import re
import json
import csv
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup

URL = "https://racing.hkjc.com/racing/english/racing-info/racing_course_time.aspx"
OUT_DIR = Path("data")
JSON_PATH = OUT_DIR / "hkjc_course_times.json"
CSV_PATH = OUT_DIR / "hkjc_course_times.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9,zh-HK;q=0.8,zh;q=0.7",
}

def clean_text(s):
    if s is None:
        return ""
    return re.sub(r"\s+", " ", s).strip()

def fetch_html():
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def parse_tables(html):
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    return tables

def extract_sectional_data_from_table(table):
    rows = table.find_all("tr")
    parsed_rows = []
    for tr in rows:
        cells = tr.find_all(["th", "td"])
        vals = [clean_text(c.get_text(" ", strip=True)) for c in cells]
        if vals:
            parsed_rows.append(vals)
    return parsed_rows

def locate_sha_tin_section(tables):
    for table in tables:
        text = clean_text(table.get_text(" ", strip=True))
        if "Sha Tin Turf Track" in text and "Reference Sectional Times" in text:
            return table
    return None

def locate_record_times_table(tables):
    for table in tables:
        text = clean_text(table.get_text(" ", strip=True))
        if "All record times only include race winners" in text:
            return table
    return None

def parse_course_time_page(html):
    soup = BeautifulSoup(html, "html.parser")
    text = clean_text(soup.get_text(" ", strip=True))

    tables = soup.find_all("table")

    data = {
        "source_url": URL,
        "scraped_at": datetime.now().isoformat(timespec="seconds"),
        "sha_tin_turf": {
            "standard_times": {},
            "sectional_times": {},
            "record_times": []
        }
    }

    table_rows = [extract_sectional_data_from_table(t) for t in tables]

    for rows in table_rows:
        flat = " | ".join([" | ".join(r) for r in rows[:3]])
        if "Sha Tin Turf Track" in flat and "Standard Times" in flat:
            headers = None
            for r in rows:
                if "Distance(M)" in r:
                    headers = r
                    break
            if headers:
                for r in rows:
                    if len(r) >= 6 and re.fullmatch(r"\d{3,4}", r[0]):
                        dist = r[0]
                        data["sha_tin_turf"]["standard_times"][dist] = {
                            "1": r[1] if len(r) > 1 else "",
                            "2": r[2] if len(r) > 2 else "",
                            "3": r[3] if len(r) > 3 else "",
                            "4": r[4] if len(r) > 4 else "",
                            "5": r[5] if len(r) > 5 else "",
                        }

        if "Sha Tin Turf Track" in flat and "Start-800M" in flat:
            for r in rows:
                if len(r) >= 2 and re.fullmatch(r"\d{3,4}", r[0]):
                    dist = r[0]
                    segs = {}
                    for idx, key in enumerate(r[1:], start=1):
                        seg_name = [
                            "start_800",
                            "800_400",
                            "400_finish",
                            "start_1200",
                            "1200_800",
                            "start_1600",
                            "1600_1200",
                            "start_2000",
                            "2000_1600",
                        ][idx - 1] if idx - 1 < 9 else f"col_{idx}"
                        segs[seg_name] = key
                    data["sha_tin_turf"]["sectional_times"][dist] = segs

        if "All record times only include race winners" in flat:
            for r in rows:
                if len(r) >= 4 and re.fullmatch(r"\d{3,4}", r[0]):
                    data["sha_tin_turf"]["record_times"].append({
                        "distance": r[0],
                        "horse_name": r[1],
                        "time": r[2],
                        "weight_lbs": r[3],
                        "date": r[4] if len(r) > 4 else ""
                    })

    return data

def export_json(data):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with JSON_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def export_csv(data):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    turf = data["sha_tin_turf"]

    for dist, stds in turf["standard_times"].items():
        sec = turf["sectional_times"].get(dist, {})
        rows.append({
            "distance": dist,
            "class1": stds.get("1", ""),
            "class2": stds.get("2", ""),
            "class3": stds.get("3", ""),
            "class4": stds.get("4", ""),
            "class5": stds.get("5", ""),
            "start_800": sec.get("start_800", ""),
            "800_400": sec.get("800_400", ""),
            "400_finish": sec.get("400_finish", ""),
            "start_1200": sec.get("start_1200", ""),
            "1200_800": sec.get("1200_800", ""),
            "start_1600": sec.get("start_1600", ""),
            "1600_1200": sec.get("1600_1200", ""),
            "start_2000": sec.get("start_2000", ""),
            "2000_1600": sec.get("2000_1600", ""),
        })

    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["distance"])
        writer.writeheader()
        if rows:
            writer.writerows(rows)

def main():
    print("Fetching HKJC course time page...")
    html = fetch_html()
    print("Parsing...")
    data = parse_course_time_page(html)
    print("Exporting JSON...")
    export_json(data)
    print("Exporting CSV...")
    export_csv(data)
    print(f"Done. JSON: {JSON_PATH}, CSV: {CSV_PATH}")

if __name__ == "__main__":
    main()