import json
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup


def crawl_example_site():
    """
    특정 매체에서 '수소' 관련 기사만 추려서 리스트로 반환하는 예시 함수.
    실제로는 해당 매체의 검색/섹션 URL, CSS 선택자에 맞게 수정해야 함.
    """
    url = "https://example.com/search?q=수소"  # 실제 매체 검색 URL로 변경
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    articles = []

    # 아래 선택자 부분은 실제 사이트 구조에 맞게 변경 필요
    for item in soup.select(".news-item"):  # 예: 기사 하나를 감싸는 div
        title_el = item.select_one(".news-title a")
        date_el = item.select_one(".news-date")
        source = "예시매체"

        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        link = title_el.get("href")

        # 상대경로일 경우 절대 URL로 보정
        if link and link.startswith("/"):
            link = "https://example.com" + link

        date_text = date_el.get_text(strip=True) if date_el else datetime.now().strftime("%Y-%m-%d")
        # 필요시 date_text → YYYY-MM-DD로 파싱하는 로직 추가

        article = {
            "date": date_text,
            "source": source,
            "title": title,
            "url": link,
            "summary": "",  # 나중에 본문 일부를 사용해 요약 생성 가능
            "tags": make_tags(title),
        }
        articles.append(article)

    return articles


def make_tags(title: str) -> list:
    """
    제목 키워드 기반으로 단순 태그 부여.
    나중에 규칙을 더 늘리거나, 요약/본문까지 같이 활용해도 됨.
    """
    title = title or ""
    tags = []

    if "연료전지" in title:
        tags.append("연료전지")
    if "수소" in title:
        tags.append("수소")
    if "암모니아" in title:
        tags.append("암모니아")
    if "CCUS" in title or "탄소포집" in title:
        tags.append("CCUS")

    return tags


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    all_articles = []

    # 여기서 매체별 크롤링 함수를 여러 개 호출해서 합칠 수 있음
    all_articles.extend(crawl_example_site())

    # 날짜 필터(선택): 오늘 기사만 남기고 싶으면 아래 필터 수행
    all_articles = [
        a for a in all_articles
        if (a.get("date") or "").startswith(today)
    ]

    out_file = data_dir / f"{today}.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)

    print(f"{len(all_articles)}건 저장 완료: {out_file}")


if __name__ == "__main__":
    main()
