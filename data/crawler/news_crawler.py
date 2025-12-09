import json
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

# -----------------------------
# 1) 기본 설정
# -----------------------------

BASE_URL = "https://www.gasnews.com"

GASNEWS_LIST_URL = (
    "https://www.gasnews.com/news/articleList.html?"
    "page={page}&sc_section_code=S1N9&view_type="
)

ELECTIMES_BASE_URL = "https://www.electimes.com"
ELECTIMES_LIST_URL = (
    "https://www.electimes.com/news/articleList.html?page={page}&view_type=sm"
)

# -----------------------------
# 2) 공통 수소 키워드
# -----------------------------

HYDROGEN_KEYWORDS = [
    "수소", "연료전지", "그린수소", "청정수소", "블루수소",
    "PAFC", "SOFC", "MCFC",
    "수전해", "전해조", "PEMEC", "AEM", "알카라인", "PEM", "CCUS",
    "암모니아", "암모니아크래킹", "CCU", "ESS", "기후부", "입찰시장", "배터리",
    "수소생산", "수소저장", "액화수소", "배출권", "하이드로젠",
    "충전소", "수소버스", "수소차",
    "한수원", "두산퓨얼셀", "한화임팩트", "현대차",
    "HPS", "REC", "RPS",
]

def contains_hydrogen_keyword(text: str) -> bool:
    text = text.lower()
    return any(kw.lower() in text for kw in HYDROGEN_KEYWORDS)


# -----------------------------
# 3) 날짜 처리
# -----------------------------

def normalize_gasnews_date(raw: str) -> str:
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
# 4) 상세 본문 추출
# -----------------------------

def extract_article_body(url: str) -> str:
    """기사 상세 본문을 가져온다"""
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 가스신문
        body_el = soup.select_one("div#article-view-content-div")
        if body_el:
            return body_el.get_text(" ", strip=True)

        # 전기신문
        body_el = soup.select_one("div#articleBody") or soup.select_one("div#article-view-content-div")
        if body_el:
            return body_el.get_text(" ", strip=True)

        return ""
    except:
        return ""


# -----------------------------
# 5) 요약기 (3줄 요약)
# -----------------------------

def summarize_3lines(text: str) -> str:
    text = text.replace("•", ". ").replace("·", ". ")
    sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 10]

    if len(sentences) == 0:
        return text[:150]

    return "\n".join(sentences[:3])


# -----------------------------
# 6) 카드뉴스 텍스트 변환
# -----------------------------

def summarize_to_cardnews(summary_text: str) -> list[str]:
    lines = summary_text.split("\n")
    return lines[:3]


# -----------------------------
# 7) 카드뉴스 이미지 생성기 연결
# -----------------------------

from cardnews_image import make_cardnews_image


# -----------------------------
# 8) 태그 생성기
# -----------------------------

def make_tags(title: str) -> list[str]:
    tags = [kw for kw in HYDROGEN_KEYWORDS if kw.lower() in title.lower()]
    return list(dict.fromkeys(tags))


# -----------------------------
# 9) 가스신문 크롤러
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

            if not contains_hydrogen_keyword(title):
                continue

            date_el = li.select_one("em.info.dated")
            date_str = normalize_gasnews_date(date_el.get_text(strip=True))

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
# 10) 전기신문 크롤러
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

            summary_el = li.select_one("p.lead a.replace-read")
            summary = summary_el.get_text(strip=True) if summary_el else ""

            combined = f"{title} {summary}".lower()
            if not contains_hydrogen_keyword(combined):
                continue

            date_el = li.select_one("em.replace-date")
            date_str = normalize_electimes_date(date_el.get_text(strip=True))

            body = extract_article_body(article_url)

            results.append({
                "date": date_str,
                "source": "전기신문",
                "title": title,
                "summary": summary,
                "url": article_url,
                "body": body,
                "tags": make_tags(title)
            })

    return results


# -----------------------------
# 11) HTML 생성기
# -----------------------------

def make_html_page(articles, out_path):
    html = """
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>오늘의 수소 뉴스 카드뉴스</title>
<style>
body { font-family: sans-serif; background:#111; color:#fff; margin:40px; }
.card { margin-bottom: 60px; border-bottom:1px solid #444; padding-bottom:40px; }
img { width:450px; margin-top:20px; }
h2 { color:#00AEEF; }
</style>
</head>
<body>

<h1>오늘의 수소 뉴스 카드뉴스</h1>
"""

    for a in articles:
        html += f"""
<div class="card">
  <h2>{a['title']}</h2>
  <a href="{a['url']}" style="color:#88c;">원문 보기</a>
  <p>{a['summary'].replace("\n","<br>")}</p>
  <img src="../data/{a['image']}" alt="card" />
</div>
"""
    html += "</body></html>"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)


# -----------------------------
# 12) 메인 함수
# -----------------------------

def main():
    today = datetime.now().strftime("%Y-%m-%d")

    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)

    all_articles = []

    all_articles.extend(crawl_gasnews(max_pages=3))
    all_articles.extend(crawl_electimes(max_pages=3))

    today_articles = [a for a in all_articles if a["date"] == today]

    html_articles = []

    for idx, a in enumerate(today_articles, start=1):
        summary_3 = summarize_3lines(a["body"])
        a["summary"] = summary_3

        card_lines = summarize_to_cardnews(summary_3)

        image_filename = f"{today}_{idx}.png"
        image_path = f"data/{image_filename}"

        make_cardnews_image(card_lines, image_path)
        a["image_filename"] = image_filename

        html_articles.append({
            "title": a["title"],
            "url": a["url"],
            "summary": a["summary"],
            "image": image_filename
        })

    json_path = data_dir / f"{today}.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(today_articles, f, ensure_ascii=False, indent=2)

    make_html_page(html_articles, "docs/index.html")

    print(f"완료: {len(today_articles)}건 저장")


# -----------------------------
# 13) 실행
# -----------------------------
if __name__ == "__main__":
    main()
