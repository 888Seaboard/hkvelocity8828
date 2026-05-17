from pathlib import Path
import json
import csv
import re
from collections import OrderedDict

import pdfplumber

PDF_PATH = Path("Pao-Dao-Biao-Zhun-Ji-Ji-Lu-Shi-Jian-Can-Kao-Zi-Liao-Sai-Ma-Zi-Xun-Xiang-Gang-Sai-Ma-Hui.pdf")
OUT_DIR = Path("data")
JSON_PATH = OUT_DIR / "hkjc_course_times.json"
CSV_PATH = OUT_DIR / "hkjc_course_times.csv"

OUT_DIR.mkdir(parents=True, exist_ok=True)

FALLBACK = {
    "standard_times": {
        "1000": {"1": "0.55.90", "2": "0.56.05", "3": "0.56.45", "4": "0.56.65", "5": "0.57.00"},
        "1200": {"1": "1.08.15", "2": "1.08.45", "3": "1.08.65", "4": "1.09.00", "5": "1.09.35"},
        "1400": {"1": "1.21.10", "2": "1.21.25", "3": "1.21.45", "4": "1.21.65", "5": "1.22.00"},
        "1600": {"1": "1.33.90", "2": "1.34.05", "3": "1.34.25", "4": "1.34.70", "5": "1.34.90"},
        "1800": {"1": "1.47.10", "2": "1.47.30", "3": "1.47.50", "4": "1.47.85", "5": "1.48.45"},
        "2000": {"1": "2.00.50", "2": "2.01.20", "3": "2.01.70", "4": "2.01.90", "5": "2.02.35"},
        "2400": {"1": "2.27.00"},
    },
    "sectional_times": {
        "1000": {"start_800": "13.05", "800_400": "20.60", "400_finish": "22.25"},
        "1200": {"start_800": "23.55", "800_400": "22.20", "400_finish": "22.40"},
        "1400": {"start_1200": "13.50", "1200_800": "22.35", "800_400": "22.85", "400_finish": "22.40"},
        "1600": {"start_1200": "24.85", "1200_800": "23.05", "800_400": "23.25", "400_finish": "22.75"},
        "1800": {"start_1600": "14.05", "1600_1200": "22.80", "1200_800": "24.00", "800_400": "23.50", "400_finish": "22.75"},
        "2000": {"start_1600": "25.95", "1600_1200": "23.90", "1200_800": "23.90", "800_400": "23.55", "400_finish": "23.20"},
        "2400": {"start_2000": "25.60", "2000_1600": "24.50", "1600_1200": "25.35", "1200_800": "23.85", "800_400": "23.75", "400_finish": "23.95"},
    }
}

def norm_time(s):
    if s is None:
        return ""
    s = str(s).strip()
    s = s.replace("：", ":").replace("﹕", ":")
    s = re.sub(r"\s+", "", s)
    return s

def extract_text(pdf_path):
    texts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            texts.append(txt)
    return "\n".join(texts)

def parse_standard_times(text):
    data = {}
    m = re.search(r"Sha Tin Turf Track(.*?)(Happy Valley Turf Track|Sha Tin All Weather Track)", text, re.S)
    if not m:
        return data
    block = m.group(1)

    for dist in ["1000", "1200", "1400", "1600", "1800", "2000", "2200", "2400"]:
        dm = re.search(rf"{dist}\s+([0-9\.\- ]+)", block)
        if not dm:
            continue
        tail = dm.group(1)
        times = re.findall(r"\d+\.\d{2}\.\d{2}", tail)
        if not times:
            times = re.findall(r"\d+[:\.]\d{2}[:\.]\d{2}", tail)
        if times:
            data[dist] = {str(i+1): norm_time(t) for i, t in enumerate(times[:5])}
    return data

def parse_sectional_times(text):
    data = {}
    sec_block = re.search(r"Standard Times & Reference Sectional Times(.*?)(Class Record Times|Record Times|班次紀錄時間)", text, re.S)
    if not sec_block:
        sec_block = re.search(r"Sha Tin Turf Track(.*?)(Happy Valley Turf Track|Sha Tin All Weather Track)", text, re.S)
    block = sec_block.group(1) if sec_block else text

    distance_keys = ["1000", "1200", "1400", "1600", "1800", "2000", "2400"]
    segment_map = {
        "1000": ["start_800", "800_400", "400_finish"],
        "1200": ["start_800", "800_400", "400_finish"],
        "1400": ["start_1200", "1200_800", "800_400", "400_finish"],
        "1600": ["start_1200", "1200_800", "800_400", "400_finish"],
        "1800": ["start_1600", "1600_1200", "1200_800", "800_400", "400_finish"],
        "2000": ["start_1600", "1600_1200", "1200_800", "800_400", "400_finish"],
        "2400": ["start_2000", "2000_1600", "1600_1200", "1200_800", "800_400", "400_finish"],
    }

    for dist in distance_keys:
        dm = re.search(rf"{dist}[\s\S]{{0,500}}", block)
        if not dm:
            continue
        snippet = dm.group(0)
        times = re.findall(r"\d+\.\d{2}\.\d{2}", snippet)
        if not times:
            times = re.findall(r"\d+[:\.]\d{2}[:\.]\d{2}", snippet)
        if times:
            keys = segment_map[dist]
            data[dist] = {k: norm_time(v) for k, v in zip(keys, times[-len(keys):])}
    return data

def merge_with_fallback(parsed):
    out = {"standard_times": {}, "sectional_times": {}}
    for dist, vals in FALLBACK["standard_times"].items():
        out["standard_times"][dist] = vals.copy()
    for dist, vals in FALLBACK["sectional_times"].items():
        out["sectional_times"][dist] = vals.copy()

    for dist, vals in parsed.get("standard_times", {}).items():
        out["standard_times"].setdefault(dist, {}).update(vals)

    for dist, vals in parsed.get("sectional_times", {}).items():
        out["sectional_times"].setdefault(dist, {}).update(vals)

    return out

def build_records(data):
    rows = []
    all_dists = sorted(set(data["standard_times"]) | set(data["sectional_times"]), key=lambda x: int(x))
    for dist in all_dists:
        std = data["standard_times"].get(dist, {})
        sec = data["sectional_times"].get(dist, {})
        row = {
            "distance": dist,
            "class1": std.get("1", ""),
            "class2": std.get("2", ""),
            "class3": std.get("3", ""),
            "class4": std.get("4", ""),
            "class5": std.get("5", ""),
            "start_800": sec.get("start_800", ""),
            "start_1200": sec.get("start_1200", ""),
            "start_1600": sec.get("start_1600", ""),
            "start_2000": sec.get("start_2000", ""),
            "2000_1600": sec.get("2000_1600", ""),
            "1600_1200": sec.get("1600_1200", ""),
            "1200_800": sec.get("1200_800", ""),
            "800_400": sec.get("800_400", ""),
            "400_finish": sec.get("400_finish", ""),
        }
        rows.append(row)
    return rows

def main():
    text = extract_text(PDF_PATH)
    parsed_std = parse_standard_times(text)
    parsed_sec = parse_sectional_times(text)

    merged = merge_with_fallback({
        "standard_times": parsed_std,
        "sectional_times": parsed_sec,
    })

    payload = {
        "source_pdf": PDF_PATH.name,
        "source": "HKJC Standard Times & Reference Sectional Times PDF",
        "sha_tin_turf": merged,
    }

    with JSON_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    rows = build_records(merged)
    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved JSON: {JSON_PATH}")
    print(f"Saved CSV: {CSV_PATH}")
    print(f"Parsed standard distances: {len(parsed_std)}")
    print(f"Parsed sectional distances: {len(parsed_sec)}")
    print(f"Total exported rows: {len(rows)}")

if __name__ == "__main__":
    main()