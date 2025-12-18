import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
from pathlib import Path
import re

# ==========================================
# 1. 설정
# ==========================================

KEYWORDS = [
    "수소", "연료전지", "그린수소", "청정수소", "블루수소", "원자력",
    "PAFC", "SOFC", "MCFC", "PEM", "재생", "배출권", "히트펌프", "도시가스", "구역전기", "PPA",
    "수전해", "전해조", "PEMEC", "AEM", "알카라인", "분산", "NDC", "핑크수소",
    "암모니아", "암모니아크래킹", "CCU", "CCUS", "기후부", "ESS", "배터리",
    "수소생산", "수소저장", "액화수소",
    "충전소", "수소버스", "수소차",
    "한수원", "두산퓨얼셀", 
    "HPS", "REC", "RPS"
]

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

ALL_JSON_PATH = DATA_DIR / "all.json"         # 누적(검색용)
LATEST_JSON_PATH = DATA_DIR / "latest.json"   # 최신일(빠른 로딩용)

MAX_PAGES = 3

# ==========================================
# 2. 유틸 함수
# ==========================================

def get_soup(url: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        return BeautifulSoup(res.text, "html.parser")
    except Exception as e:
        print(f"[ERROR] {url} → {e}")
        return None

def check_keywords(text: str):
    lower = (text or "").lower()
    return [kw for kw in KEYWORDS if kw.lower() in lower]

def normalize_date_common(raw: str):
    if not raw:
        return datetime.now().strftime("%Y-%m-%d")

    raw = raw.strip()

    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    year = datetime.now().year
    try:
        return datetime.strptime(f"{year}.{raw}", "%Y.%m.%d %H:%M").strftime("%Y-%m-%d")
    except Exception:
        try:
            return datetime.strptime(f"{year}.{raw}", "%Y.%m.%d").strftime("%Y-%m-%d")
        except Exception:
            return datetime.now().strftime("%Y-%m-%d")

def extract_article_body(url: str) -> str:
    soup = get_soup(url)
    if not soup:
        return ""

    body_el = soup.select_one(
        "div#article-view-content-div, "
        "div.article-body, "
        "div#articleBody, "
        "div.article-text"
    )

    if not body_el:
        texts = [p.get_text(" ", strip=True) for p in soup.select("p")]
    else:
        texts = [x.get_text(" ", strip=True) for x in body_el.find_all(["p", "span", "div"])]

    body = " ".join(texts)
    return re.sub(r"\s+", " ", body).strip()

def split_sentences(text: str):
    if not text:
        return []
    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = cleaned.replace("다. ", "다.\n").replace("다.", "다.\n")
    parts = re.split(r"(?<=[.!?])\s+", cleaned)

    sentences = []
    for p in parts:
        for seg in p.split("\n"):
            seg = seg.strip()
            if seg:
                sentences.append(seg)
    return sentences

def summarize_body(body: str, max_lines: int = 2) -> str:
    sents = split_sentences(body)
    return " ".join(sents[:max_lines]).strip() if sents else ""

def is_h2_related(title: str, body: str):
    # 제목 + 본문 모두 기준으로 키워드 판단
    tags = sorted(set(check_keywords(title) + check_keywords(body)))
    return (len(tags) > 0), tags

# ==========================================
# 3. 크롤러 (1~3페이지)
# ==========================================

def crawl_energy_news(max_pages=3):
    print("   [에너지신문] 크롤링...")
    results = []
    base_url = "https://www.energy-news.co.kr"

    for page in range(1, max_pages + 1):
        url = f"{base_url}/news/articleList.html?page={page}&view_type=sm"
        soup = get_soup(url)
        if not soup:
            continue

        for art in soup.select("#section-list .type1 li"):
            try:
                a = art.select_one("h2.titles a") or art.select_one("h4.titles a")
                if not a:
                    continue

                title = a.get_text(strip=True)
                link = a.get("href", "")
                if link and not link.startswith("http"):
                    link = base_url + link

                raw_date = (art.select_one("em.info.dated") or {}).get_text(strip=True) if art.select_one("em.info.dated") else ""
                date = normalize_date_common(raw_date)

                body = extract_article_body(link)
                ok, tags = is_h2_related(title, body)
                if not ok:
                    continue

                subtitle = summarize_body(body, max_lines=2)

                results.append({
                    "source": "에너지신문",
                    "title": title,
                    "url": link,
                    "date": date,
                    "tags": tags,
                    "subtitle": subtitle,
                    "is_important": True
                })
            except Exception:
                continue
    return results

def crawl_gas_news(max_pages=3):
    print("   [가스신문] 크롤링...")
    results = []
    base_url = "https://www.gasnews.com"

    for page in range(1, max_pages + 1):
        url = f"{base_url}/news/articleList.html?page={page}&sc_section_code=S1N9&view_type="
        soup = get_soup(url)
        if not soup:
            continue

        for art in soup.select("section#section-list ul.type1 > li"):
            try:
                a = art.select_one("h4.titles a") or art.select_one("h2.titles a")
                if not a:
                    continue

                title = a.get_text(strip=True)
                link = a.get("href", "")
                if link and not link.startswith("http"):
                    link = base_url + link

                raw_date = (art.select_one("em.info.dated") or {}).get_text(strip=True) if art.select_one("em.info.dated") else ""
                date = normalize_date_common(raw_date)

                body = extract_article_body(link)
                ok, tags = is_h2_related(title, body)
                if not ok:
                    continue

                subtitle = summarize_body(body, max_lines=2)

                results.append({
                    "source": "가스신문",
                    "title": title,
                    "url": link,
                    "date": date,
                    "tags": tags,
                    "subtitle": subtitle,
                    "is_important": True
                })
            except Exception:
                continue
    return results

def crawl_electric_news(max_pages=3):
    print("   [전기신문] 크롤링...")
    results = []
    base_url = "https://www.electimes.com"

    for page in range(1, max_pages + 1):
        url = f"{base_url}/news/articleList.html?page={page}&view_type=sm"
        soup = get_soup(url)
        if not soup:
            continue

        for art in soup.select("#section-list .type1 li"):
            try:
                a = art.select_one("h2.titles a") or art.select_one("h4.titles a")
                if not a:
                    continue

                title = a.get_text(strip=True)
                link = a.get("href", "")
                if link and not link.startswith("http"):
                    link = base_url + link

                raw_date = (art.select_one("em.info.dated") or {}).get_text(strip=True) if art.select_one("em.info.dated") else ""
                date = normalize_date_common(raw_date)

                body = extract_article_body(link)
                ok, tags = is_h2_related(title, body)
                if not ok:
                    continue

                subtitle = summarize_body(body, max_lines=2)

                results.append({
                    "source": "전기신문",
                    "title": title,
                    "url": link,
                    "date": date,
                    "tags": tags,
                    "subtitle": subtitle,
                    "is_important": True
                })
            except Exception:
                continue
    return results

# ==========================================
# 4. 저장 로직 (중복제거 + 날짜별 + 누적)
# ==========================================

def dedup_by_url(items):
    d = {}
    for it in items:
        if it.get("url"):
            d[it["url"]] = it
    return list(d.values())

def load_existing_all():
    if not ALL_JSON_PATH.exists():
        return []
    try:
        with ALL_JSON_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []

def save_json(path: Path, data):
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def job():
    print(f"\n[크롤링 시작] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    all_data = []
    all_data.extend(crawl_energy_news(MAX_PAGES))
    all_data.extend(crawl_gas_news(MAX_PAGES))
    all_data.extend(crawl_electric_news(MAX_PAGES))

    all_data = dedup_by_url(all_data)

    # 날짜별로 저장
    by_date = {}
    for a in all_data:
        by_date.setdefault(a["date"], []).append(a)

    for d, items in by_date.items():
        items = dedup_by_url(items)
        items.sort(key=lambda x: (x.get("is_important", False), x.get("source", ""), x.get("title", "")), reverse=True)
        save_json(DATA_DIR / f"{d}.json", items)

    # 누적(all.json) 업데이트 (기존 + 신규 merge 후 URL 기준 dedup)
    existing_all = load_existing_all()
    merged = dedup_by_url(existing_all + all_data)

    # 누적본은 날짜 최신순 → (동일 날짜면 소스/제목)
    merged.sort(key=lambda x: (x.get("date", ""), x.get("is_important", False)), reverse=True)
    save_json(ALL_JSON_PATH, merged)

    # latest.json은 “가장 최신 날짜”만 뽑아서 저장
    latest_date = max(by_date.keys()) if by_date else datetime.now().strftime("%Y-%m-%d")
    latest_items = by_date.get(latest_date, [])
    latest_items = dedup_by_url(latest_items)
    latest_items.sort(key=lambda x: (x.get("is_important", False),), reverse=True)
    save_json(LATEST_JSON_PATH, latest_items)

    print(f"[완료] 날짜별 {len(by_date)}개 파일 + all.json + latest.json 생성")

if __name__ == "__main__":
    job()
