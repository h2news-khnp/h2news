import json
import re
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

# -------------------------------------------------------
# 1. 기본 설정
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
# 2. 수소 키워드 (공통 필터)
# -------------------------------------------------------

HYDROGEN_KEYWORDS = [
    "수소", "연료전지", "그린수소", "청정수소", "블루수소", "청정수소", "원자력",
    "PAFC", "SOFC", "MCFC", "PEM", "재생", "배출권", "히트펌프", "도시가스", "구역전기", "PPA",
    "수전해", "전해조", "PEMEC", "AEM", "알카라인", "분산", "NDC", "핑크수소",
    "암모니아", "암모니아크래킹", "CCU", "CCUS", "기후부", "ESS", "배터리",
    "수소생산", "수소저장", "액화수소",
    "충전소", "수소버스", "수소차", "인프라",
    "한수원", "두산퓨얼셀", "한화임팩트", "현대차",
    "HPS", "HPC", "REC", "RPS"
]

def contains_hydrogen_keyword(text: str) -> bool:
    text = text.lower()
    return any(kw.lower() in text for kw in HYDROGEN_KEYWORDS)


# -------------------------------------------------------
# 3. 날짜 변환
# -------------------------------------------------------

def normalize_gasnews_date(raw: str) -> str:
    raw = raw.strip()
    year = datetime.now().year
    try:
        return datetime.strptime(f"{year}.{raw}", "%Y.%m.%d %H:%M").strftime("%Y-%m-%d")
    except:
        try:
            return datetime.strptime(f"{year}.{raw}", "%Y.%m.%d").strftime("%Y-%m-%d")
        except:
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
# 4. 태그 생성
# -------------------------------------------------------

def make_tags(title: str) -> list[str]:
    tags = [kw for kw in HYDROGEN_KEYWORDS if kw.lower() in title.lower()]
    return list(dict.fromkeys(tags))


# -------------------------------------------------------
# 5. 문장 분리
# -------------------------------------------------------

def split_sentences(text: str) -> list[str]:
    if not text:
        return []

    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = cleaned.replace("다. ", "다.\n")
    cleaned = cleaned.replace("다.", "다.\n")

    parts = re.split(r"(?<=[.!?])\s+", cleaned)

    sentences = []
    for p in parts:
        for seg in p.split("\n"):
            seg = seg.strip()
            if seg:
                sentences.append(seg)

    return sentences


# -------------------------------------------------------
# 6. 2문장 요약(subtitle)
# -------------------------------------------------------

def extract_subtitle(body: str, max_sentences: int = 2) -> str:
    if not body:
        return ""
    sents = split_sentences(body)
    return " ".join(sents[:max_sentences])


# -------------------------------------------------------
# 7. 기사 본문 크롤링
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

    texts = [x.get_text(" ", strip=True) for x in body_el.find_all(["p", "span", "div"])]
    body = " ".join(texts)
    return re.sub(r"\s+", " ", body).strip()


# -------------------------------------------------------
# 8. 가스신문 크롤러
# -------------------------------------------------------

def crawl_gasnews(max_pages: int = 3) -> list[dict]:
    results = []

    for page in range(1, max_pages + 1):
        url = GASNEWS_LIST_URL.format(page=page)
        print(f"[가스신문] {page} 페이지 → {url}")

        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for li in soup.select("section#section-list ul.type1 > li"):
            title_a = li.select_one("h4.titles a")
            if not title_a:
                continue

            title = title_a.get_text(strip=True)
            article_url = BASE_URL + title_a.get("href", "")

            date_el = li.select_one("em.info.dated")
            date_str = normalize_gasnews_date(date_el.get_text(strip=True))

            # 키워드 필터링
            if not contains_hydrogen_keyword(title):
                continue

            body = extract_article_body(article_url)
            subtitle = extract_subtitle(body, max_sentences=2)

            results.append({
                "date": date_str,
                "source": "가스신문",
                "title": title,
                "subtitle": subtitle,
                "url": article_url,
                "tags": make_tags(title)
            })

    return results


# -------------------------------------------------------
# 9. 전기신문 크롤러
# -------------------------------------------------------

def crawl_electimes(max_pages: int = 3) -> list[dict]:
    results = []

    for page in range(1, max_pages + 1):
        url = ELECTIMES_LIST_URL.format(page=page)
        print(f"[전기신문] {page} 페이지 → {url}")

        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for li in soup.select("#section-list ul.type > li.item"):
            title_a = li.select_one("h4.titles a.replace-titles")
            if not title_a:
                continue

            title = title_a.get_text(strip=True)
            article_url = ELECTIMES_BASE_URL + title_a.get("href", "")

            date_el = li.select_one("em.replace-date")
            date_str = normalize_electimes_date(date_el.get_text(strip=True))

            summary_el = li.select_one("p.lead a.replace-read")
            summary_text = summary_el.get_text(strip=True) if summary_el else ""

            if not contains_hydrogen_keyword(f"{title} {summary_text}"):
                continue

            body = extract_article_body(article_url)
            subtitle = extract_subtitle(body, max_sentences=2)

            results.append({
                "date": date_str,
                "source": "전기신문",
                "title": title,
                "subtitle": subtitle,
                "url": article_url,
                "tags": make_tags(title)
            })

    return results


# -------------------------------------------------------
# 10. 메인 로직 (중복 제거 + JSON 저장)
# -------------------------------------------------------

def main():
    today = datetime.now().strftime("%Y-%m-%d")

    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    # 기사 수집
    collected = []
    collected.extend(crawl_gasnews(max_pages=3))
    collected.extend(crawl_electimes(max_pages=3))

    # URL 기준 중복 제거
    unique = {}
    for a in collected:
        unique[a["url"]] = a

    deduped_articles = list(unique.values())

    # 오늘 기사만 저장
    today_articles = [a for a in deduped_articles if a["date"] == today]

    # today.json 생성
    out_file = data_dir / f"{today}.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(today_articles, f, ensure_ascii=False, indent=2)

    # latest.json 생성 (index.html이 참고)
    latest_file = data_dir / "latest.json"
    with latest_file.open("w", encoding="utf-8") as f:
        json.dump(today_articles, f, ensure_ascii=False, indent=2)

    print(f"✔ 완료: {len(today_articles)}건 저장됨 (중복 제거 완료)")


if __name__ == "__main__":
    main()
