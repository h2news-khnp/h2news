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
    "PAFC", "SOFC", "MCFC", "PEM",
    "수전해", "전해조", "PEMEC", "AEM", "알카라인",
    "암모니아", "암모니아크래킹", "CCU", "CCUS",
    "REC", "RPS", "ESS", "배터리",
    "한수원", "두산퓨얼셀", "한화임팩트", "현대차"
]

BASE_DIR = Path("data")
DAILY_DIR = BASE_DIR / "daily"
BASE_DIR.mkdir(exist_ok=True)
DAILY_DIR.mkdir(exist_ok=True)

LATEST_JSON = BASE_DIR / "latest.json"
TODAY = datetime.now().strftime("%Y-%m-%d")
TODAY_JSON = DAILY_DIR / f"{TODAY}.json"

# ==========================================
# 2. 공통 유틸
# ==========================================

def get_soup(url):
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        res.raise_for_status()
        return BeautifulSoup(res.text, "html.parser")
    except Exception:
        return None


def normalize_date(raw):
    if not raw:
        return TODAY
    raw = raw.strip()
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    year = datetime.now().year
    try:
        return datetime.strptime(f"{year}.{raw}", "%Y.%m.%d").strftime("%Y-%m-%d")
    except Exception:
        return TODAY


def extract_body(url):
    soup = get_soup(url)
    if not soup:
        return ""
    body = soup.select_one(
        "div#article-view-content-div, div#articleBody, div.article-body"
    )
    texts = body.get_text(" ", strip=True) if body else ""
    return re.sub(r"\s+", " ", texts)


def is_related(title, body):
    text = f"{title} {body}".lower()
    return any(k.lower() in text for k in KEYWORDS)


def extract_tags(title, body):
    text = f"{title} {body}".lower()
    return [k for k in KEYWORDS if k.lower() in text]


def summarize(body):
    sents = re.split(r"(?<=다\.)\s+|(?<=[.!?])\s+", body)
    return " ".join(sents[:2]).strip()

# ==========================================
# 3. 신문별 크롤러 (1~3페이지)
# ==========================================

def crawl(base_url, source):
    results = []
    for page in range(1, 4):
        url = f"{base_url}/news/articleList.html?page={page}&view_type=sm"
        soup = get_soup(url)
        if not soup:
            continue

        for li in soup.select("#section-list .type1 li"):
            a = li.select_one("h2.titles a, h4.titles a")
            if not a:
                continue

            title = a.get_text(strip=True)
            link = a["href"]
            if not link.startswith("http"):
                link = base_url + link

            date_raw = li.select_one("em.info.dated")
            date = normalize_date(date_raw.get_text(strip=True) if date_raw else "")

            body = extract_body(link)
            if not is_related(title, body):
                continue

            results.append({
                "source": source,
                "title": title,
                "url": link,
                "date": date,
                "subtitle": summarize(body),
                "tags": extract_tags(title, body)
            })

    return results

# ==========================================
# 4. 실행
# ==========================================

def run():
    all_articles = []
    all_articles += crawl("https://www.energy-news.co.kr", "에너지신문")
    all_articles += crawl("https://www.gasnews.com", "가스신문")
    all_articles += crawl("https://www.electimes.com", "전기신문")

    # URL 기준 중복 제거
    unique = {a["url"]: a for a in all_articles}.values()
    articles = sorted(unique, key=lambda x: x["date"], reverse=True)

    # 날짜별 JSON 저장
    with TODAY_JSON.open("w", encoding="utf-8") as f:
        json.dump(list(articles), f, ensure_ascii=False, indent=2)

    # latest.json = 오늘 기사만
    today_articles = [a for a in articles if a["date"] == TODAY]
    with LATEST_JSON.open("w", encoding="utf-8") as f:
        json.dump(today_articles, f, ensure_ascii=False, indent=2)

    print(f"[완료] {TODAY_JSON.name} / latest.json 생성 ({len(today_articles)}건)")

# ==========================================
# 5. 엔트리포인트
# ==========================================

if __name__ == "__main__":
    run()
