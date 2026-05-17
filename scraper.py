from playwright.sync_api import sync_playwright
import pandas as pd
import time
import random
import re
import os

BASE = "https://racing.hkjc.com"


def norm_text(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def safe_get_attr(el, attr):
    try:
        return el.get_attribute(attr) or ""
    except:
        return ""


def extract_replay_url_from_cells(cells):
    for i in range(cells.count()):
        try:
            c = cells.nth(i)
            a = c.locator("a[href]")
            if a.count() > 0:
                href = safe_get_attr(a.first, "href")
                if href:
                    return BASE + href if href.startswith("/") else href
        except:
            continue
    return ""


def parse_racecourse_raw(v):
    v = norm_text(v)
    if not v:
        return "", "", "", ""
    m = re.match(r"(.+?)(草地|泥地)(.*)", v)
    if m:
        racecourse = m.group(1).strip()
        track = m.group(2).strip()
        course = m.group(3).strip().strip('"').strip("'")
        return v, racecourse, track, course
    return v, v, "", ""


def scrape_trainer_horses(page, trainer_id, limit_per_trainer=100, debug=True):
    url = f"{BASE}/zh-hk/local/information/listbystable?trainerid={trainer_id}"
    if debug:
        print(f"   ↳ Open trainer page: {url}")

    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except:
        pass

    if debug:
        try:
            print("   ↳ title:", page.title())
        except:
            pass

    horses = []
    seen = set()

    links = page.locator('a[href*="horseid="]')
    count = links.count()

    if debug:
        print(f"   ↳ horse links found: {count}")

    for i in range(count):
        try:
            link = links.nth(i)
            name = norm_text(link.inner_text())
            href = safe_get_attr(link, "href")
            m = re.search(r"horseid=([^&]+)", href, re.I)
            horse_id = m.group(1) if m else ""
            if not horse_id or horse_id in seen:
                continue
            seen.add(horse_id)
            horses.append({"horse_name": name, "horse_id": horse_id, "trainer_id": trainer_id})
            if debug and len(horses) <= 5:
                print(f"      + {name} | {horse_id}")
            if len(horses) >= limit_per_trainer:
                break
        except Exception as e:
            if debug:
                print(f"      ! link parse failed: {e}")
            continue

    if debug:
        print(f"   ↳ total collected: {len(horses)}")

    return horses[:limit_per_trainer]


def scrape_horse_form_records(page, horse_id, debug=False):
    url = f"{BASE}/zh-hk/local/information/horse?horseid={horse_id}&Option=1"
    if debug:
        print(f"   ↳ open horse page: {url}")

    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except:
        pass

    if debug:
        try:
            print("   ↳ title:", page.title())
        except:
            pass
        try:
            bodytxt = norm_text(page.locator("body").inner_text(timeout=5000))
            print("   ↳ body head:", bodytxt[:1200])
        except:
            pass

    try:
        tabs = page.locator("a:has-text('往績紀錄'), a:has-text('Horse Form Records'), a:has-text('Form Records')")
        if tabs.count() > 0:
            tabs.first.click(timeout=5000)
            page.wait_for_timeout(2000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except:
                pass
    except:
        pass

    tables = page.locator("table")
    tcount = tables.count()
    if debug:
        print(f"   ↳ tables found: {tcount}")

    target_table = None
    target_index = -1

    for ti in range(tcount):
        try:
            txt = norm_text(tables.nth(ti).inner_text(timeout=5000))
            if debug:
                print(f"   ↳ table[{ti}] head: {txt[:400]}")
            if ("場次" in txt and "名次" in txt and "日期" in txt and "途程" in txt) or ("Race Index" in txt and "Date" in txt):
                target_table = tables.nth(ti)
                target_index = ti
                break
        except:
            continue

    if not target_table:
        if debug:
            print("   ↳ no target table found")
        return []

    trs = target_table.locator("tr")
    trcount = trs.count()
    if debug:
        print(f"   ↳ use table[{target_index}], trcount={trcount}")

    rows = []
    headers = []
    current_season = ""

    for ri in range(trcount):
        try:
            tr = trs.nth(ri)
            cells = tr.locator("th, td")
            ccount = cells.count()
            texts = [norm_text(cells.nth(ci).inner_text()) for ci in range(ccount)]
            if debug:
                print(f"   ↳ row[{ri}] texts: {texts}")

            if not texts:
                continue

            if len(texts) == 1 and (("Season" in texts[0]) or re.search(r"\d{2}/\d{2}", texts[0]) or "馬季" in texts[0]):
                current_season = texts[0]
                continue

            if texts and (("場次" in texts[0]) or ("Race Index" in texts[0]) or ("名次" in texts[0]) or ("Date" in texts[0])):
                headers = texts
                if debug:
                    print("   ↳ headers:", headers)
                continue

            if len(texts) < 8:
                continue

            if headers and len(texts) == len(headers):
                data = dict(zip(headers, texts))
            else:
                if len(texts) >= 18:
                    data = {
                        "Race Index": texts[0],
                        "Pla.": texts[1],
                        "Date": texts[2],
                        "RC/Track/ Course": texts[3],
                        "Dist.": texts[4],
                        "G": texts[5],
                        "Race Class": texts[6],
                        "Dr.": texts[7],
                        "Rtg.": texts[8],
                        "Trainer": texts[9],
                        "Jockey": texts[10],
                        "LBW": texts[11],
                        "Win Odds": texts[12],
                        "Act. Wt.": texts[13],
                        "Running Position": texts[14],
                        "Finish Time": texts[15],
                        "Declar. Horse Wt.": texts[16],
                        "Gear": texts[17],
                    }
                else:
                    continue

            racecourse_raw = data.get("RC/Track/ Course", data.get("RC/Track/Course", data.get("馬場/跑道/ 賽道", "")))
            _, racecourse, track, course = parse_racecourse_raw(racecourse_raw)

            row = {
                "horse_id": horse_id,
                "season": current_season,
                "race_index": data.get("Race Index", data.get("場次", "")),
                "placing": data.get("Pla.", data.get("Placing", data.get("名次", ""))),
                "date": data.get("Date", data.get("日期", "")),
                "racecourse_raw": racecourse_raw,
                "racecourse": racecourse,
                "track": track,
                "course": course,
                "distance": data.get("Dist.", data.get("途程", "")),
                "going": data.get("G", data.get("場地狀況", "")),
                "race_class": data.get("Race Class", data.get("賽事班次", "")),
                "draw": data.get("Dr.", data.get("檔位", "")),
                "rating": data.get("Rtg.", data.get("評分", "")),
                "trainer": data.get("Trainer", data.get("練馬師", "")),
                "jockey": data.get("Jockey", data.get("騎師", "")),
                "lbw": data.get("LBW", data.get("頭馬距離", "")),
                "win_odds": data.get("Win Odds", data.get("獨贏賠率", "")),
                "actual_wt": data.get("Act. Wt.", data.get("實際負磅", "")),
                "running_position": data.get("Running Position", data.get("沿途走位", "")),
                "finish_time": data.get("Finish Time", data.get("完成時間", "")),
                "decl_horse_wt": data.get("Declar. Horse Wt.", data.get("排位體重", "")),
                "gear": data.get("Gear", data.get("配備", "")),
                "replay_url": extract_replay_url_from_cells(cells) if ccount > 0 else ""
            }
            rows.append(row)

        except Exception as e:
            if debug:
                print(f"   ↳ row[{ri}] parse fail: {e}")
            continue

    if debug:
        print(f"   ↳ parsed rows: {len(rows)}")

    return rows


def scrape_hkjc_horses(limit_per_trainer=100, max_trainers=30, debug=False):
    print("🚀 啟動 HKJC 全練馬師爬蟲（完整往績版）...")
    rows = []

    trainers = [
        ("鄭俊偉", "CCW"), ("桂福特", "CBJ"), ("告東尼", "CAS"), ("游達榮", "EDJ"), ("方嘉柏", "FC"),
        ("賀賢", "HAD"), ("大衛希斯", "HDA"), ("羅富全", "LFC"), ("呂健威", "LKW"), ("文家良", "MKL"),
        ("巫偉傑", "MWK"), ("廖康銘", "NM"), ("伍鵬志", "NPC"), ("黎昭昇", "RW"), ("沈集成", "SCS"),
        ("蔡約翰", "SJJ"), ("蘇偉賢", "SWY"), ("丁冠豪", "TKH"), ("徐雨石", "TYS"), ("韋達", "WDJ"),
        ("葉楚航", "YCH"), ("姚本輝", "YPF")
    ]

    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=random.choice(user_agents),
            extra_http_headers={
                "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
                "DNT": "1"
            }
        )
        page = context.new_page()

        total_horses = 0
        total_records = 0

        for i, (trainer_name, trainer_id) in enumerate(trainers[:max_trainers]):
            try:
                print(f"\n🔍 [{i+1}/{min(max_trainers, len(trainers))}] {trainer_name} ({trainer_id})...")
                time.sleep(random.uniform(1.0, 2.0))

                horses = scrape_trainer_horses(page, trainer_id, limit_per_trainer=limit_per_trainer, debug=debug)
                print(f"   → 找到 {len(horses)} 匹")

                for h in horses:
                    try:
                        time.sleep(random.uniform(0.8, 1.5))
                        detail_rows = scrape_horse_form_records(page, h["horse_id"], debug=debug)

                        if not detail_rows:
                            rows.append({
                                "horse_name": h["horse_name"],
                                "horse_id": h["horse_id"],
                                "trainer_name": trainer_name,
                                "trainer_id": trainer_id
                            })
                            total_records += 1
                        else:
                            for r in detail_rows:
                                r["horse_name"] = h["horse_name"]
                                r["trainer_name"] = trainer_name
                                r["trainer_id"] = trainer_id
                                rows.append(r)
                                total_records += 1

                        total_horses += 1
                        if total_horses % 20 == 0:
                            print(f"   → 已處理 {total_horses} 匹，累計 {total_records} 行往績")
                    except Exception as e:
                        print(f"   ⚠️ {h['horse_name']} 失敗：{e}")
                        continue

                print(f"   ✅ {trainer_name} 完成！累計 {total_horses} 匹")
            except Exception as e:
                print(f"❌ {trainer_name} 失敗：{e}")
                time.sleep(random.uniform(2, 5))
                continue

        context.close()
        browser.close()

    df = pd.DataFrame(rows)
    print(f"\n🎉 完成！總計 {len(df)} 行資料")
    return df


if __name__ == "__main__":
    df = scrape_hkjc_horses(limit_per_trainer=100, max_trainers=30, debug=False)
    out = "hkjc_horse_history.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"saved to {out}")
    print(df.head())