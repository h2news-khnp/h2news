import json
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# -----------------------------
# 1. 기본 설정
# -----------------------------

# 가스신문
BASE_URL = "https://www.gasnews.com"
LIST_URL = (
    "https://www.gasnews.com/news/articleList.html"
    "?page={page}&sc_section_code=&view_type="  # 제목형(view_type 비움)
)

# 전기신문
ELECTIMES_BASE_URL = "https://www.electimes.com"
ELECTIMES_LIST_URL = (
    "https://www.electimes.com/news/articleList.html?page={page}&view_type=sm"
)

# -----------------------------
# 2. 공통 키워드(가스신문 + 전기신문 모두 사용)
# -----------------------------

hydrogen_keywords = [
    # 기본 수소/연료전지
    "수소", "연료전지", "수전해", "전해조", "그린수소", "청정수소",
    "암모니아", "암모니아크래킹",

    # 확장 키워드
    "블루수소", "그레이수소", "수소생산", "수소공급", "수소전환",
    "PEM", "AEM", "SOEC", "알칼라인",
    "SOFC", "MCFC", "PAFC",
    "분산전원", "발전소", "REC", "SMP",

    "수소충전소", "액화수소", "수소저장", "수소 배관", "모빌리티",

    "CHPS", "CCUS", "탄소중립", "RE100", "Net Zero",

    # 기업 키워드
    "두산퓨얼셀", "한화임팩트", "포스코", "현대차", "한수원",
]

# -----------------------------
# 3. 날짜 포맷 변환 함수
# -----------------------------

def normalize_gasnews_short_date(raw: str) -> str:
    """
    가스신문: '12.09 09:50' 같은 형식을 'YYYY-MM-DD'로 변환.
    연도는 실행 시점의 현재 연도를 사용.
    """
    raw = (raw or "").strip()
    if not raw:
        return datetime.now().strftime("%Y-%m-%d")

    year = datetime.now().year

    # raw 예: "12.09 09:50" 또는 "12.09"
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(f"{year}.{raw}", fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return datetime.now().strftime("%Y-%m-%d")


def normalize_electimes_date(raw: str) -> str:
    """
    전기신문: '2025.12.09 16:26' 또는 '2025.12.09' 형태 -> 'YYYY-MM-DD'
    """
    raw = (raw or "").strip()
    if not raw:
        return datetime.now().strftime("%Y-%m-%d")

    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return datetime.now().strftime("%Y-%m-%d")


# -----------------------------
# 4. 태그 자동 부여 함수
# -----------------------------

def make_tags(title: str) -> list[str]:
    title = title or ""
    tags: list[str] = []

    if "수소" in title:
        tags.append("수소")
    if "연료전지" in title or "PAFC" in title or "SOFC" in title or "MCFC" in title:
        tags.append("연료전지")
    if "수전해" in title or "전해조" in title or "PEMEC" in title or "알카라인" in title:
        tags.append("수소생산")
        tags.append("수전해")
    if "암모니아" in title:
        tags.append("수소생산")
        tags.append("암모니아")
    if "충전소" in title:
        tags.append("수소인프라")
        tags.append("충전소")
    if any(k in title for k in ["법", "시행령", "시행규칙", "고시", "지침"]):
        tags.append("정책")

    if "한수원" in title:
        tags.append("한수원")
    if "두산퓨얼셀" in title:
        tags.append("두산퓨얼셀")
    if "한화임팩트" in title:
        tags.append("한화임팩트")

    # 중복 제거
    return list(dict.fromkeys(tags))


# -----------------------------
# 5. 가스신문 전체기사 목록 크롤링
# -----------------------------

def crawl_gasnews_total(max_pages: int = 1) -> list[dict]:
    """
    가스신문 '전체기사' 목록에서
    공통 hydrogen_keywords 기반으로 수소/에너지 관련 기사만 수집
    """
    results: list[dict] = []

    for page in range(1, max_pages + 1):
        url = LIST_URL.format(page=page)
        print(f"[가스신문 전체기사] 페이지 {page} 크롤링: {url}")

        resp = requests.get(url, timeout=10)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # section#section-list 안의 ul.type1 > li 가 기사 1건
        for li in soup.select("section#section-list ul.type1 > li"):
            title_el = li.select_one("h4.titles a")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            href = title_el.get("href") or ""

            # 상대경로 -> 절대경로
            if href.startswith("/"):
                link = BASE_URL + href
            else:
                link = href

            category_el = li.select_one("em.info.category")
            category = category_el.get_text(strip=True) if category_el else ""

            date_el = li.select_one("em.info.dated")
            raw_date = date_el.get_text(strip=True) if date_el else ""
            date_str = normalize_gasnews_short_date(raw_date)

            # 제목 기준으로 hydrogen_keywords 필터
            text_for_filter = title
            if not any(k in text_for_filter for k in hydrogen_keywords):
                # 카테고리가 '수소·연료전지'면 예외적으로 포함
                if category != "수소·연료전지":
                    continue

            article = {
                "date": date_str,
                "source": "가스신문",
                "title": title,
                "url": link,
                "summary": "",
                "tags": make_tags(title),
                "category": category,
                "thumb": "",  # 가스신문 목록에는 썸네일이 따로 안 보이면 공란
            }
            results.append(article)

    return results


# -----------------------------
# 6. 전기신문 전체기사(요약형) 크롤링
# -----------------------------

def crawl_electimes(max_pages: int = 1, only_hydrogen: bool = True) -> list[dict]:
    """
    전기신문 '전체기사' 요약형(view_type=sm)에서
    hydrogen_keywords 기반으로 필터링
    """
    results: list[dict] = []

    for page in range(1, max_pages + 1):
        list_url = ELECTIMES_LIST_URL.format(page=page)
        print(f"[전기신문] page={page} GET {list_url}")

        resp = requests.get(list_url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for li in soup.select("#section-list ul.type > li.item"):
            title_a = li.select_one("div.view-cont h4.titles a.linked.replace-titles")
            if not title_a:
                continue

            title = title_a.get_text(strip=True)
            href = title_a.get("href") or ""
            if href.startswith("/"):
                url = ELECTIMES_BASE_URL + href
            else:
                url = href

            date_el = li.select_one("div.view-cont em.replace-date")
            raw_date = date_el.get_text(strip=True) if date_el else ""
            date_str = normalize_electimes_date(raw_date)

            summary_a = li.select_one("div.view-cont p.lead a.replace-read")
            summary = summary_a.get_text(strip=True) if summary_a else ""

            thumb_img = li.select_one("a.linked.thumb img.replace-thumb")
            thumb_url = ""
            if thumb_img and thumb_img.get("src"):
                thumb_src = thumb_img.get("src")
                if thumb_src.startswith("http"):
                    thumb_url = thumb_src
                else:
                    thumb_url = ELECTIMES_BASE_URL + thumb_src

            if only_hydrogen:
                text_for_filter = f"{title} {summary}"
                if not any(k in text_for_filter for k in hydrogen_keywords):
                    continue

            article = {
                "date": date_str,
                "source": "전기신문",
                "title": title,
                "url": url,
                "summary": summary,
                "tags": make_tags(title),
                "category": "",
                "thumb": thumb_url,
            }
            results.append(article)

    return results


# -----------------------------
# 7. main 함수
# -----------------------------

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    articles: list[dict] = []

    # 가스신문 수집
    gas_articles = crawl_gasnews_total(max_pages=2)

    # 전기신문 수집
    electimes_articles = crawl_electimes(max_pages=2, only_hydrogen=True)

    articles.extend(gas_articles)
    articles.extend(electimes_articles)

    # 오늘 날짜 기사만 필터링하고 싶을 때
    articles = [
        a for a in articles
        if (a.get("date") or "").startswith(today)
    ]

    out_file = data_dir / f"{today}.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"{len(articles)}건 저장 완료: {out_file}")


# -----------------------------
# 8. 스크립트 진입점
# -----------------------------

if __name__ == "__main__":
    main()
