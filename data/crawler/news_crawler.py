import json
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

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

MAX_PAGES = 3
TIMEOUT = 12

DATA_DIR = Path("data")
BY_DATE_DIR = DATA_DIR / "by_date"
DATA_DIR.mkdir(exist_ok=True)
BY_DATE_DIR.mkdir(exist_ok=True)

ALL_JSON_PATH = DATA_DIR / "all.json"
LATEST_JSON_PATH = DATA_DIR / "latest.json"

ENERGY_BASE = "https://www.energy-news.co.kr"
GAS_BASE = "https://www.gasnews.com"
ELECT_BASE = "https://www.electimes.com"

ENERGY_LIST = ENERGY_BASE + "/news/articleList.html?page={page}&view_type=sm"
GAS_LIST = GAS_BASE + "/news/articleList.html?page={page}&view_type=sm"
ELECT_LIST = ELECT_BASE + "/news/articleList.html?page={page}&view_type=sm"

# ==========================================
# 2. 공통 유틸
# ==========================================

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()

def get_soup(url: str):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=TIMEOUT)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"[ERROR] {url} → {e}")
        return None

def parse_date(raw: str) -> str:
    raw = (raw or "").strip()
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    year = datetime.now().year
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            return datetime.strptime(f"{year}.{raw}", fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return datetime.now().strftime("%Y-%m-%d")

def contains_keyword(text: str) -> bool:
    low = (text or "").lower()
    return any(k.lower() in low for k in KEYWORDS)

def make_tags(text: str) -> list:
    low = (text or "").lower()
    seen = set()
    tags = []
    for k in KEYWORDS:
        if k.lower() in low and k not in seen:
            tags.append(k)
            seen.add(k)
    return tags

# ==========================================
# 3. 본문 정제 (🔥 전기신문 핵심 수정)
# ==========================================

def clean_electimes_noise(text: str) -> str:
    """
    전기신문 본문에서 기자/제보/공유 등 잡음 제거
    """
    s = normalize_spaces(text)

    # 이메일 제거
    s = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", " ", s)

    # 전기신문에 자주 섞이는 안내/공유/제보 문구 제거
    noise_patterns = [
        r"제보\s*제보", r"제보", r"기사보내기", r"기사\s*보내기",
        r"페이스북\(?\)?로\s*기사보내기", r"트위터\(?\)?로\s*기사보내기",
        r"카카오톡\(?\)?으로\s*기사보내기", r"밴드\(?\)?로\s*기사보내기",
        r"공유", r"SNS", r"좋아요", r"구독",
        r"무단전재\s*및\s*재배포\s*금지",
    ]
    for pat in noise_patterns:
        s = re.sub(pat, " ", s, flags=re.IGNORECASE)

    # 기자명 표기(예: 홍길동 기자 / 홍길동 기자(aaa@bbb.com))
    s = re.sub(r"[가-힣]{2,4}\s*기자(\([^)]*\))?", " ", s)

    return normalize_spaces(s)

# ==========================================
# 4. 본문 추출
# ==========================================

def extract_body(url: str) -> str:
    soup = get_soup(url)
    if not soup:
        return ""

    selectors = [
        "div#article-view-content-div",
        "div#articleBody",
        "div.article-body",
        "div.article-text",
        "article"
    ]

    body_el = None
    for sel in selectors:
        body_el = soup.select_one(sel)
        if body_el:
            break

    texts = []
    if body_el:
        for t in body_el.find_all(["p", "span", "div"]):
            txt = t.get_text(" ", strip=True)
            if txt:
                texts.append(txt)
    else:
        for p in soup.select("p"):
            txt = p.get_text(" ", strip=True)
            if txt:
                texts.append(txt)

    body = normalize_spaces(" ".join(texts))
    body = clean_article_body(body)

    return body if len(body) >= 40 else ""

# ==========================================
# 5. 목록 크롤러 (1~3페이지)
# ==========================================

def crawl_list(list_url, base_url, source):
    results = []

    for page in range(1, MAX_PAGES + 1):
        soup = get_soup(list_url.format(page=page))
        if not soup:
            continue

        items = soup.select("#section-list li")
        kept = 0

        for li in items:
            try:
                a = li.select_one("h2.titles a, h4.titles a, a.replace-titles")
                if not a:
                    continue

                title = a.get_text(strip=True)
                href = a.get("href", "")
                url = href if href.startswith("http") else base_url + href

                date_el = li.select_one("em.info.dated")
                date = parse_date(date_el.get_text(strip=True) if date_el else "")

                body = extract_body(url)

                if not (contains_keyword(title) or contains_keyword(body)):
                    continue

                tags = make_tags(title + " " + body)
                subtitle = summarize_2lines(body)

                results.append({
                    "source": source,
                    "title": title,
                    "url": url,
                    "date": date,
                    "tags": tags,
                    "subtitle": subtitle,
                    "is_important": 1 if tags else 0
                })
                kept += 1
            except Exception:
                continue

        print(f"[{source}] page {page} → {kept}건")

    return results

# ==========================================
# 6. 저장 로직
# ==========================================

def job():
    print(f"\n[크롤링 시작] {now_str()}")

    new_items = []
    new_items += crawl_list(ENERGY_LIST, ENERGY_BASE, "에너지신문")
    new_items += crawl_list(GAS_LIST, GAS_BASE, "가스신문")
    new_items += crawl_list(ELECT_LIST, ELECT_BASE, "전기신문")

    # 누적 병합
    existing = json.loads(ALL_JSON_PATH.read_text("utf-8")) if ALL_JSON_PATH.exists() else []
    merged = {i["url"]: i for i in existing + new_items}.values()
    merged = sorted(merged, key=lambda x: (x["date"], x["is_important"]), reverse=True)

    ALL_JSON_PATH.write_text(json.dumps(list(merged), ensure_ascii=False, indent=2), encoding="utf-8")

    # 날짜별 저장
    by_date = {}
    for i in merged:
        by_date.setdefault(i["date"], []).append(i)

    for d, lst in by_date.items():
        (BY_DATE_DIR / f"{d}.json").write_text(
            json.dumps(lst, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    latest_date = max(by_date.keys())
    LATEST_JSON_PATH.write_text(
        json.dumps(by_date[latest_date], ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"[완료] 총 {len(merged)}건 | 최신날짜 {latest_date}")

if __name__ == "__main__":
    job()
