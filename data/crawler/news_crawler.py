import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re

# =========================
# 0. KST 기준 "오늘" 유틸
# =========================
KST = timezone(timedelta(hours=9))

def now_kst():
    return datetime.now(KST)

def today_kst_str():
    return now_kst().strftime("%Y-%m-%d")

# =========================
# 1. 설정
# =========================
KEYWORDS = [
    "수소", "연료전지", "그린수소", "청정수소", "블루수소", "원자력",
    "PAFC", "SOFC", "MCFC", "PEM", "재생", "배출권", "히트펌프", "도시가스", "구역전기", "PPA",
    "수전해", "전해조", "PEMEC", "AEM", "알카라인", "분산", "NDC", "핑크수소",
    "암모니아", "암모니아크래킹", "CCU", "CCUS", "기후부", "ESS", "배터리",
    "수소생산", "수소저장", "액화수소",
    "충전소", "수소버스", "수소차", "인프라",
    "한수원", "두산퓨얼셀", 
    "HPS", "REC", "RPS"
]

DATA_DIR = Path("data")
DAILY_DIR = DATA_DIR / "daily"
DATA_DIR.mkdir(exist_ok=True)
DAILY_DIR.mkdir(parents=True, exist_ok=True)

LATEST_JSON_PATH = DATA_DIR / "latest.json"

# =========================
# 2. 유틸 함수
# =========================
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
    """
    파싱 실패 시 '오늘'을 넣지 말고 None 반환.
    -> 날짜별 아카이빙 정확도를 위해 필수.
    """
    if not raw:
        return None

    raw = raw.strip()

    # 날짜 문자열에서 숫자/구분자만 최대한 남김
    cleaned = re.sub(r"[^0-9\.\:\-\s]", " ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # 1) 연도 포함 케이스
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 2) 연도 미포함 케이스: "12.17 09:30", "12.17"
    year = now_kst().year
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            return datetime.strptime(f"{year}.{cleaned}", fmt).strftime("%Y-%m-%d")
        except Exception:
            pass

    return None

# =========================
# 3. 본문/요약
# =========================
def extract_article_body(url: str) -> str:
    soup = get_soup(url)
    if not soup:
        return ""

    body_el = soup.select_one(
        "div#article-view-content-div, div.article-body, div#articleBody, div.article-text"
    )
    if not body_el:
        texts = [p.get_text(" ", strip=True) for p in soup.select("p")]
    else:
        texts = [x.get_text(" ", strip=True) for x in body_el.find_all(["p", "span", "div"])]

    body = " ".join(texts)
    body = re.sub(r"\s+", " ", body).strip()
    return body

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
    if not sents:
        return ""
    return " ".join(sents[:max_lines]).strip()

# =========================
# 4. 상세페이지에서 날짜 추출(가능하면)
# =========================
def extract_article_date(url: str, fallback: str):
    soup = get_soup(url)
    if not soup:
        return fallback

    # 사이트별 날짜가 있는 영역 후보를 넓게 탐색
    candidates = [
        "em.info.dated",
        "span.date",
        "span.datetime",
        "div.article-head-info span",
        "li.datetime",
        "p.info span",
    ]

    text = ""
    for sel in candidates:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            text = el.get_text(" ", strip=True)
            break

    # fallback: 페이지 전체에서 패턴 검색
    if not text:
        all_text = soup.get_text(" ", strip=True)
        m = re.search(r"(\d{4}\.\d{2}\.\d{2}\s*\d{2}:\d{2})", all_text)
        if m:
            text = m.group(1)
        else:
            m = re.search(r"(\d{4}\.\d{2}\.\d{2})", all_text)
            if m:
                text = m.group(1)

    parsed = normalize_date_common(text) if text else None
    return parsed or fallback

# =========================
# 5. 크롤러(1~3페이지)
# =========================
def crawl_energy_news(max_pages: int = 3):
    results = []
    base_url = "https://www.energy-news.co.kr"
    for page in range(1, max_pages + 1):
        url = f"{base_url}/news/articleList.html?page={page}&view_type=sm"
        print(f"   [에너지신문] {page}p → {url}")

        soup = get_soup(url)
        if not soup:
            continue

        items = soup.select("#section-list .type1 li")
        for it in items:
            try:
                a = it.select_one("h2.titles a")
                if not a:
                    continue
                title = a.get_text(strip=True)
                link = a.get("href", "")
                if not link.startswith("http"):
                    link = base_url + link

                # 목록 날짜
                date_el = it.select_one("em.info.dated")
                list_date = normalize_date_common(date_el.get_text(strip=True) if date_el else "")  # None 가능

                # 본문 키워드 판단(제목+본문)
                body = extract_article_body(link)
                tags = check_keywords(f"{title} {body}")
                if not tags:
                    continue

                # 날짜는 상세에서 재확인(실패 시 목록 날짜)
                date = extract_article_date(link, list_date)

                # 날짜를 못 얻으면 저장에서 제외(아카이브 정확도 우선)
                if not date:
                    continue

                results.append({
                    "source": "에너지신문",
                    "title": title,
                    "url": link,
                    "date": date,
                    "tags": tags,
                    "subtitle": summarize_body(body, 2),
                    "is_important": True
                })
            except Exception:
                continue
    return results

def crawl_gas_news(max_pages: int = 3):
    results = []
    base_url = "https://www.gasnews.com"
    for page in range(1, max_pages + 1):
        url = f"{base_url}/news/articleList.html?page={page}&view_type=sm"
        print(f"   [가스신문] {page}p → {url}")

        soup = get_soup(url)
        if not soup:
            continue

        items = soup.select("#section-list .type1 li")
        for it in items:
            try:
                a = it.select_one("h2.titles a") or it.select_one("h4.titles a")
                if not a:
                    continue
                title = a.get_text(strip=True)
                link = a.get("href", "")
                if not link.startswith("http"):
                    link = base_url + link

                date_el = it.select_one("em.info.dated")
                list_date = normalize_date_common(date_el.get_text(strip=True) if date_el else "")

                body = extract_article_body(link)
                tags = check_keywords(f"{title} {body}")
                if not tags:
                    continue

                date = extract_article_date(link, list_date)
                if not date:
                    continue

                results.append({
                    "source": "가스신문",
                    "title": title,
                    "url": link,
                    "date": date,
                    "tags": tags,
                    "subtitle": summarize_body(body, 2),
                    "is_important": True
                })
            except Exception:
                continue
    return results

def crawl_electric_news(max_pages: int = 3):
    results = []
    base_url = "https://www.electimes.com"
    for page in range(1, max_pages + 1):
        url = f"{base_url}/news/articleList.html?page={page}&view_type=sm"
        print(f"   [전기신문] {page}p → {url}")

        soup = get_soup(url)
        if not soup:
            continue

        items = soup.select("#section-list .type1 li")
        for it in items:
            try:
                a = it.select_one("h2.titles a") or it.select_one("h4.titles a")
                if not a:
                    continue
                title = a.get_text(strip=True)
                link = a.get("href", "")
                if not link.startswith("http"):
                    link = base_url + link

                date_el = it.select_one("em.info.dated")
                list_date = normalize_date_common(date_el.get_text(strip=True) if date_el else "")

                body = extract_article_body(link)
                tags = check_keywords(f"{title} {body}")
                if not tags:
                    continue

                date = extract_article_date(link, list_date)
                if not date:
                    continue

                results.append({
                    "source": "전기신문",
                    "title": title,
                    "url": link,
                    "date": date,
                    "tags": tags,
                    "subtitle": summarize_body(body, 2),
                    "is_important": True
                })
            except Exception:
                continue
    return results

# =========================
# 6. 저장: 날짜별 daily + latest.json(최신 날짜)
# =========================
def job():
    print(f"\n[크롤링 시작] {now_kst().strftime('%Y-%m-%d %H:%M:%S')} (KST)")

    all_data = []
    all_data.extend(crawl_energy_news(3))
    all_data.extend(crawl_gas_news(3))
    all_data.extend(crawl_electric_news(3))

    # URL 기준 중복 제거
    dedup = {}
    for a in all_data:
        dedup[a["url"]] = a
    unique = list(dedup.values())

    # date 기준 그룹핑 저장
    by_date = {}
    for a in unique:
        by_date.setdefault(a["date"], []).append(a)

    # 각 날짜 파일 저장(덮어쓰기 갱신)
    for d, items in by_date.items():
        items.sort(key=lambda x: (x["source"], x["title"]))
        out = DAILY_DIR / f"{d}.json"
        with out.open("w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

    # latest.json은 가장 최신 날짜 파일을 가리키게 생성
    if by_date:
        latest_date = sorted(by_date.keys())[-1]
        latest_items = by_date[latest_date]
        with LATEST_JSON_PATH.open("w", encoding="utf-8") as f:
            json.dump(latest_items, f, ensure_ascii=False, indent=2)
        print(f"[완료] {len(unique)}건 / 최신날짜={latest_date} → daily/*.json + latest.json")
    else:
        # 아무것도 못 건졌으면 빈 배열이라도 생성(인덱스 오류 방지)
        with LATEST_JSON_PATH.open("w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        print("[완료] 수집 0건 → latest.json 빈 배열 생성")

if __name__ == "__main__":
    job()
