import json
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# -----------------------------
# 1. 기본 설정
# -----------------------------

BASE_URL = "https://www.gasnews.com"

# 가스신문 전체기사 목록 (제목형)
LIST_URL = (
    "https://www.gasnews.com/news/articleList.html"
    "?page={page}&sc_section_code=&view_type="  # 제목형(view_type 비움)
)


# -----------------------------
# 2. 날짜 포맷 변환 함수
#    예: "12.09 09:50" -> "2025-12-09"
# -----------------------------

def normalize_gasnews_short_date(raw: str) -> str:
    """
    '12.09 09:50' 같은 형식을 'YYYY-MM-DD'로 변환.
    연도는 실행 시점의 현재 연도를 사용.
    """
    raw = (raw or "").strip()
    if not raw:
        return datetime.now().strftime("%Y-%m-%d")

    year = datetime.now().year

    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(f"{year}.{raw}", fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # 형식 안 맞으면 일단 오늘 날짜로
    return datetime.now().strftime("%Y-%m-%d")


# -----------------------------
# 3. 태그 자동 부여 함수
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
# 4. 가스신문 전체기사 목록 크롤링 함수
# -----------------------------

def crawl_gasnews_total(max_pages: int = 1) -> list[dict]:
    """
    가스신문 '전체기사' 목록에서
    수소·연료전지 관련 기사만 추려서 가져오는 크롤러.
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

            # 1) 카테고리가 '수소·연료전지'인 기사
            # 2) 또는 제목에 '수소' / '연료전지' 포함된 기사만 사용
            if category != "수소·연료전지" and not (
                "수소" in title or "연료전지" in title
            ):
                continue

            article = {
                "date": date_str,
                "source": "가스신문",
                "title": title,
                "url": link,
                "summary": "",  # 필요시 상세페이지 본문 일부로 채워도 됨
                "tags": make_tags(title),
                "category": category,
            }
            results.append(article)

    return results


# -----------------------------
# 5. main 함수 (여기가 네가 말한 "4번" 위치)
# -----------------------------

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    articles: list[dict] = []

    # 가스신문 전체기사에서 수소·연료전지 관련 기사 수집
    # 페이지 범위는 필요에 따라 조정 (1~2페이지 정도부터 시작)
    articles.extend(crawl_gasnews_total(max_pages=2))

    # 오늘 날짜 기사만 남기고 싶으면 필터
    articles = [
        a for a in articles
        if (a.get("date") or "").startswith(today)
    ]

    out_file = data_dir / f"{today}.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"{len(articles)}건 저장 완료: {out_file}")


# -----------------------------
# 6. 스크립트 진입점
# -----------------------------

if __name__ == "__main__":
    main()
