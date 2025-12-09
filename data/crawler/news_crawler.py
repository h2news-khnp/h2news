import json
import re
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

# -------------------------------------------------------
# 1. 기본 URL 설정
# -------------------------------------------------------

BASE_URL = "https://www.gasnews.com"
GASNEWS_LIST_URL = (
    "https://www.gasnews.com/news/articleList.html?"
    "page={page}&sc_section_code=S1N9&view_type="
)

ELECTIMES_BASE_URL = "https://www.electimes.com"
ELECTIMES_LIST_URL = (
    "https://www.electimes.com/news/articleList.html?page={page}&view_type=sm"
)

# -------------------------------------------------------
# 2. 수소 관련 키워드
# -------------------------------------------------------

HYDROGEN_KEYWORDS = [
    "수소","연료전지","그린수소","청정수소","블루수소","재생","전해조",
    "수전해","PAFC","SOFC","MCFC","PEM","PPA","CCUS",
    "암모니아","암모니아크래킹","ESS","배터리","액화수소",
    "한수원","두산퓨얼셀","한화임팩트","현대차",
    "HPS","HPC","REC","RPS"
]

def contains_hydrogen_keyword(text: str) -> bool:
    text = text.lower()
    return any(kw.lower() in text for kw in HYDROGEN_KEYWORDS)

# -------------------------------------------------------
# 3. 날짜 변환 함수
# -------------------------------------------------------

def normalize_gasnews_date(raw: str) -> str:
    raw = raw.strip()
    year = datetime.now().year
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            return datetime.strptime(f"{year}.{raw}", fmt).strftime("%Y-%m-%d")
        except:
            continue
    return datetime.now().strftime("%Y-%m-%d")

def normalize_electimes_date(raw: str) -> str:
    raw = raw.strip()
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except:
            continue
    return datetime.now().strftime("%Y-%m-%d")

# -------------------------------------------------------
# 4. 본문 크롤링
# -------------------------------------------------------

def extract_article_body(url: str) -> str:
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except:
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")
    body_el = soup.select_one("div#article-view-content-div, div.article-body, div#articleBody")

    if not body_el:
        return ""

    texts = [x.get_text(" ", strip=True) for x in body_el.find_all(["p","span","div"])]
    body = " ".join(texts)
    return re.sub(r"\s+", " ", body).strip()

# -------------------------------------------------------
# 5. 기사 요약 (3줄 요약)
# -------------------------------------------------------

def split_sentences(text: str) -> list[str]:
    if not text:
        return []
    cleaned = re.sub(r"\s+", " ", text)
    cleaned = cleaned.replace("다. ", "다.\n")
    cleaned = cleaned.replace("다.", "다.\n")
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    sents = []
    for p in parts:
        for seg in p.split("\n"):
            seg = seg.strip()
            if seg:
                sents.append(seg)
    return sents

def summarize_body(body: str, max_lines: int = 3) -> str:
    sents = split_sentences(body)
    return "\n".join(sents[:max_lines]) if sents else ""

# -------------------------------------------------------
# 6. 가스신문 크롤러
# -------------------------------------------------------

def crawl_gasnews(max_pages: int = 3) -> list[dict]:
    results = []
    for page in range(1, max_pages + 1):
        url = GASNEWS_LIST_URL.format(page=page)
        print(f"[가스신문] {page} → {url}")

        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for li in soup.select("section#section-list ul.type1 > li"):
            title_a = li.select_one("h4.titles a")
            if not title_a:
                continue

            title = title_a.get_text(strip=True)
            if not contains_hydrogen_keyword(title):
                continue

            article_url = BASE_URL + title_a.get("href", "")
            date_str = normalize_gasnews_date(li.select_one("em.info.dated").get_text(strip=True))

            body = extract_article_body(article_url)
            summary_3 = summarize_body(body)

            results.append({
                "date": date_str,
                "source": "가스신문",
                "title": title,
                "url": article_url,
                "summary": summary_3,
                "body": body
            })
    return results

# -------------------------------------------------------
# 7. 전기신문 크롤러
# -------------------------------------------------------

def crawl_electimes(max_pages: int = 3) -> list[dict]:
    results = []
    for page in range(1, max_pages + 1):
        url = ELECTIMES_LIST_URL.format(page=page)
        print(f"[전기신문] {page} → {url}")

        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for li in soup.select("#section-list ul.type > li.item"):
            title_a = li.select_one("h4.titles a.replace-titles")
            if not title_a:
                continue

            title = title_a.get_text(strip=True)
            summary_el = li.select_one("p.lead a.replace-read")
            combined = f"{title} {summary_el.get_text(strip=True) if summary_el else ''}"

            if not contains_hydrogen_keyword(combined):
                continue

            article_url = ELECTIMES_BASE_URL + title_a.get("href", "")
            date_str = normalize_electimes_date(li.select_one("em.replace-date").get_text(strip=True))

            body = extract_article_body(article_url)
            summary_3 = summarize_body(body)

            results.append({
                "date": date_str,
                "source": "전기신문",
                "title": title,
                "url": article_url,
                "summary": summary_3,
                "body": body
            })
    return results

# -------------------------------------------------------
# 8. 메인 실행 (JSON 생성)
# -------------------------------------------------------

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    print("=== H2 News Crawling Start ===")

    all_articles = crawl_gasnews() + crawl_electimes()
    today_articles = [a for a in all_articles if a["date"] == today]

    out_path = data_dir / f"{today}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(today_articles, f, ensure_ascii=False, indent=2)

    print(f"[완료] {len(today_articles)}개 기사 저장 → {out_path}")

if __name__ == "__main__":
    main()
