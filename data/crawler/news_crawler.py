import json
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.gasnews.com"

LIST_URL = (
    "https://www.gasnews.com/news/articleList.html"
    "?page={page}&sc_section_code=&view_type="  # 제목형(view_type 빈값)
)


def normalize_gasnews_short_date(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return datetime.now().strftime("%Y-%m-%d")

    year = datetime.now().year
    # "12.09 09:50" 기준
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(f"{year}.{raw}", fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return datetime.now().strftime("%Y-%m-%d")


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

    return list(dict.fromkeys(tags))  # 중복 제거


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

        # section#section-list 안의 ul.type1 > li가 기사 1건
        for li in soup.select("section#section-list ul.type1 > li"):
            title_el = li.select_one("h4.titles a")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            href = title_el.get("href") or ""

            # 절대 URL로 보정
            if href.startswith("/"):
                link = BASE_URL + href
            else:
                link = href

            category_el = li.select_one("em.info.category")
            category = category_el.get_text(strip=True) if category_el else ""

            date_el = li.select_one("em.info.dated")
            raw_date = date_el.get_text(strip=True) if date_el else ""
            date_str = normalize_gasnews_short_date(raw_date)

            # 1) 카테고리가 '수소·연료전지'인 것만 사용
            # 2) 혹은 제목에 '수소' / '연료전지' 포함된 기사 추가
            if category != "수소·연료전지" and not (
                "수소" in title or "연료전지" in title
            ):
                continue

            article = {
                "date": date_str,
                "source": "가스신문",
                "title": title,
                "url": link,
                "summary": "",  # 필요하면 상세페이지 들어가서 본문 일부를 요약해도 됨
                "tags": make_tags(title),
                "category": category,
            }
            results.append(article)

    return results

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    articles: list[dict] = []

    # 1) 가스신문 전체기사에서 수소·연료전지 관련 기사 수집 (최근 1~2페이지 정도)
    articles.extend(crawl_gasnews_total(max_pages=2))

    # 2) 오늘 날짜 기사만 필터링하고 싶다면:
    #    (전체기사 페이지에는 어제/그제 기사도 섞여 있으니까)
    articles = [
        a for a in articles
        if (a.get("date") or "").startswith(today)
    ]

    out_file = data_dir / f"{today}.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"{len(articles)}건 저장 완료: {out_file}")


if __name__ == "__main__":
    main()

