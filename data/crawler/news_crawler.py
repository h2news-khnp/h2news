import json
import re
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

from cardnews_image import make_cardnews_image


# ---------------------------------------------------------
# 수소 관련 키워드
# ---------------------------------------------------------
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

def is_hydrogen(text):
    text = text.lower()
    return any(k.lower() in text for k in HYDROGEN_KEYWORDS)


# ---------------------------------------------------------
# 날짜 처리
# ---------------------------------------------------------
def normalize_gasnews_date(raw):
    raw = raw.strip()
    year = datetime.now().year
    for fmt in ["%Y.%m.%d %H:%M", "%Y.%m.%d"]:
        try:
            return datetime.strptime(f"{year}.{raw}", fmt).strftime("%Y-%m-%d")
        except:
            pass
    return datetime.now().strftime("%Y-%m-%d")


def normalize_electimes_date(raw):
    raw = raw.strip()
    for fmt in ["%Y.%m.%d %H:%M", "%Y.%m.%d"]:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except:
            pass
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------
# 본문 추출
# ---------------------------------------------------------
def extract_body(url):
    try:
        html = requests.get(url, timeout=10).text
        soup = BeautifulSoup(html, "html.parser")
        body_el = soup.select_one("div#articleBody")
        if not body_el:
            return ""
        text = body_el.get_text(" ", strip=True)
        return text
    except:
        return ""


# ---------------------------------------------------------
# 본문 요약 3줄
# ---------------------------------------------------------
def summarize_body(body, max_lines=3):
    body = body.replace("\r", "").replace("\n", " ")
    body = re.sub(r"\s+", " ", body).strip()

    sentences = re.split(r"(?<=[.!?])\s+", body)
    sentences = [s for s in sentences if len(s) > 5]

    return "\n".join(sentences[:max_lines])


# ---------------------------------------------------------
# 가스신문 크롤러
# ---------------------------------------------------------
def crawl_gasnews(max_pages=2):
    BASE = "https://www.gasnews.com"
    URL = "https://www.gasnews.com/news/articleList.html?page={page}&sc_section_code=S1N9&view_type="

    results = []

    for page in range(1, max_pages + 1):
        html = requests.get(URL.format(page=page), timeout=10).text
        soup = BeautifulSoup(html, "html.parser")

        for li in soup.select("section#section-list ul.type1 > li"):
            a = li.select_one("h4.titles a")
            if not a:
                continue

            title = a.get_text(strip=True)
            url = BASE + a["href"]

            date_el = li.select_one("em.info.dated")
            date = normalize_gasnews_date(date_el.get_text(strip=True))

            if not is_hydrogen(title):
                continue

            body = extract_body(url)
            summary = summarize_body(body)

            results.append({
                "date": date,
                "source": "가스신문",
                "title": title,
                "url": url,
                "body": body,
                "summary": summary,
            })

    return results


# ---------------------------------------------------------
# 전기신문 크롤러
# ---------------------------------------------------------
def crawl_electimes(max_pages=2):
    BASE = "https://www.electimes.com"
    URL = "https://www.electimes.com/news/articleList.html?page={page}&view_type=sm"

    results = []

    for page in range(1, max_pages + 1):
        html = requests.get(URL.format(page=page), timeout=10).text
        soup = BeautifulSoup(html, "html.parser")

        for li in soup.select("#section-list ul.type > li.item"):
            a = li.select_one("h4.titles a.replace-titles")
            if not a:
                continue

            title = a.get_text(strip=True)
            url = BASE + a["href"]

            date_el = li.select_one("em.replace-date")
            date = normalize_electimes_date(date_el.get_text(strip=True))

            summary_el = li.select_one("p.lead a.replace-read")
            summary_raw = summary_el.get_text(strip=True) if summary_el else ""

            if not is_hydrogen(title + " " + summary_raw):
                continue

            body = extract_body(url)
            summary = summarize_body(body)

            results.append({
                "date": date,
                "source": "전기신문",
                "title": title,
                "url": url,
                "body": body,
                "summary": summary,
            })

    return results


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
def main():
    today = datetime.now().strftime("%Y-%m-%d")

    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    articles = []
    articles.extend(crawl_gasnews())
    articles.extend(crawl_electimes())

    today_articles = [a for a in articles if a["date"] == today]

    # 카드뉴스 생성
    for idx, art in enumerate(today_articles):
        text = f"{art['title']}\n\n{art['summary']}"
        image_filename = f"{today}_{idx+1}.png"
        image_path = data_dir / image_filename

        make_cardnews_image(text, image_path)
        art["image"] = image_filename

    # JSON 저장
    out = data_dir / f"{today}.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(today_articles, f, ensure_ascii=False, indent=2)

    print(f"완료: {len(today_articles)}건 저장 / 카드뉴스 생성 완료")


if __name__ == "__main__":
    main()
