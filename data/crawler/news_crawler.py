import json
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

# -----------------------------
# 1. 기본 설정
# -----------------------------

BASE_URL = "https://www.gasnews.com"

# 가스신문의 '수소·연료전지' 카테고리
GASNEWS_LIST_URL = (
    "https://www.gasnews.com/news/articleList.html?"
    "page={page}&sc_section_code=S1N9&view_type="
)

# 전기신문
ELECTIMES_BASE_URL = "https://www.electimes.com"
ELECTIMES_LIST_URL = (
    "https://www.electimes.com/news/articleList.html?page={page}&view_type=sm"
)

# -----------------------------
# 2. 수소 관련 키워드 (전 매체 공통)
# -----------------------------
HYDROGEN_KEYWORDS = [
    # 기본
    "수소", "연료전지", "그린수소", "청정수소", "블루수소",
    "PAFC", "SOFC", "MCFC",

    # 수전해/전해조
    "수전해", "전해조", "PEMEC", "AEM", "알카라인",

    # 암모니아 기반
    "암모니아", "암모니아크래킹",

    # 인프라 & 정책
    "수소생산", "수소저장", "액화수소",
    "충전소", "수소버스", "수소차", "인프라",

    # 기관/기업 키워드
    "한수원", "두산퓨얼셀", "한화임팩트", "현대차",

    # 기타
    "HPS", "HPC", "REC", "RPS",
]

def contains_hydrogen_keyword(text: str) -> bool:
    """수소 관련 키워드 포함 여부를 검사."""
    text = text.lower()
    return any(kw.lower() in text for kw in HYDROGEN_KEYWORDS)


# -----------------------------
# 3. 날짜 변환 함수
# -----------------------------

def normalize_gasnews_date(raw: str) -> str:
    """
    ex) '12.09 09:50' → '2025-12-09'
    """
    raw = (raw or "").strip()
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


# -----------------------------
# 4. 태그 생성
# -----------------------------

def make_tags(title: str) -> list[str]:
    tags = [kw for kw in HYDROGEN_KEYWORDS if kw.lower() in title.lower()]
    return list(dict.fromkeys(tags))  # 중복 제거


# -----------------------------
# 5. 가스신문 크롤러
# -----------------------------

def crawl_gasnews(max_pages: int = 2) -> list[dict]:
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

            # 필터링
            if not contains_hydrogen_keyword(title):
                continue

            # ★ 상세 본문 추출
            body = extract_article_body(article_url)

            results.append({
                "date": date_str,
                "source": "가스신문",
                "title": title,
                "url": article_url,
                "body": body,
                "tags": make_tags(title)
            })

    return results



# -----------------------------
# 6. 전기신문 크롤러
# -----------------------------

def crawl_electimes(max_pages: int = 2) -> list[dict]:
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
            summary = summary_el.get_text(strip=True) if summary_el else ""

            # 필터링
            combined = f"{title} {summary}".lower()
            if not contains_hydrogen_keyword(combined):
                continue

            # ★ 상세 본문 추출 추가
            body = extract_article_body(article_url)

            results.append({
                "date": date_str,
                "source": "전기신문",
                "title": title,
                "url": article_url,
                "summary": summary,
                "body": body,
                "tags": make_tags(title)
            })

    return results

# -----------------------------
# 7. 카드뉴스
# -----------------------------

from cardnews_image import make_cardnews_image



# -----------------------------
# 8. 메인 (JSON 저장)
# -----------------------------

def main():
    today = datetime.now().strftime("%Y-%m-%d")

    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    all_articles = []

    # 두 신문 동시 크롤링
    all_articles.extend(crawl_gasnews(max_pages=3))
    all_articles.extend(crawl_electimes(max_pages=3))

    # 오늘 기사만 필터링
    today_articles = [a for a in all_articles if a["date"] == today]

    out_path = data_dir / f"{today}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(today_articles, f, ensure_ascii=False, indent=2)

    print(f"\n🟢 저장 완료: {len(today_articles)}건 → {out_path}\n")


# -----------------------------
# 8. 실행
# -----------------------------
if __name__ == "__main__":
    main()
