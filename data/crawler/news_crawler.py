# news_crawler.py

import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
from pathlib import Path
import os
import re

# ==========================================
# 1. 설정
# ==========================================

KEYWORDS = [
    "수소", "연료전지", "그린수소", "청정수소", "블루수소", "원자력",
    "PAFC", "SOFC", "MCFC", "PEM", "재생", "배출권", "히트펌프", "도시가스", "구역전기", "PPA",
    "수전해", "전해조", "PEMEC", "AEM", "알카라인", "분산", "NDC", "핑크수소",
    "암모니아", "암모니아크래킹", "CCU", "CCUS", "기후부", "ESS", "배터리",
    "수소생산", "수소저장", "액화수소",
    "충전소", "수소버스", "수소차", "인프라",
    "한수원", "두산퓨얼셀", "한화임팩트", "현대차",
    "HPS", "HPC", "REC", "RPS"
]

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
LATEST_JSON_PATH = DATA_DIR / "latest.json"


# ==========================================
# 2. 유틸 함수
# ==========================================

def get_soup(url: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        return BeautifulSoup(res.text, "html.parser")
    except Exception as e:
        print(f"[ERROR] {url} → {e}")
        return None

def check_keywords(title: str, body: str):
    lower_title = title.lower()
    lower_body = body.lower()
    return [kw for kw in KEYWORDS if kw.lower() in lower_title or kw.lower() in lower_body]

def normalize_date_common(raw: str):
    if not raw:
        return datetime.now().strftime("%Y-%m-%d")
    raw = raw.strip()
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    year = datetime.now().year
    try:
        return datetime.strptime(f"{year}.{raw}", "%Y.%m.%d %H:%M").strftime("%Y-%m-%d")
    except Exception:
        try:
            return datetime.strptime(f"{year}.{raw}", "%Y.%m.%d").strftime("%Y-%m-%d")
        except Exception:
            return datetime.now().strftime("%Y-%m-%d")

def extract_article_body(url: str) -> str:
    soup = get_soup(url)
    if not soup:
        return ""
    body_el = soup.select_one(
        "div#article-view-content-div, div.article-body, div#articleBody, div.article-text"
    )
    if not body_el:
        texts = [p.get_text(" ", strip=True) for p in soup.select("p")]
    else:
        texts = [x.get_text(" ", strip=True) for x in body_el.find_all(["p", "span", "div"])]
    return re.sub(r"\s+", " ", " ".join(texts)).strip()

def split_sentences(text: str):
    if not text:
        return []
    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = cleaned.replace("다. ", "다.\n").replace("다.", "다.\n")
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    sentences = []
    for p in parts:
        for seg in p.split("\n"):
            if seg.strip():
                sentences.append(seg.strip())
    return sentences

def summarize_body(body: str, max_lines: int = 2) -> str:
    sents = split_sentences(body)
    return "\n".join(sents[:max_lines]) if sents else ""


# ==========================================
# 3. 각 신문별 크롤러
# ==========================================

def crawl_site(name, base_url, page_url_template):
    print(f"   [{name}] 크롤링 시작...")
    results = []

    for page in range(1, 4):
        url = page_url_template.format(page=page)
        soup = get_soup(url)
        if not soup:
            continue

        articles = soup.select("#section-list .type1 li") or soup.select(".article-list .list-block")

        for art in articles:
            try:
                title_tag = art.select_one("h2.titles a") or art.select_one("h4.titles a")
                if not title_tag:
                    continue

                title = title_tag.get_text(strip=True)
                link = title_tag["href"]
                if not link.startswith("http"):
                    link = base_url + link

                date_tag = art.select_one("em.info.dated")
                raw_date = date_tag.get_text(strip=True) if date_tag else ""
                date = normalize_date_common(raw_date)

                body = extract_article_body(link)
                summary = summarize_body(body, max_lines=2).replace("\n", " ")
                tags = check_keywords(title, body)

                results.append({
                    "source": name,
                    "title": title,
                    "url": link,
                    "date": date,
                    "tags": tags,
                    "subtitle": summary,
                    "is_important": len(tags) > 0
                })

            except Exception:
                continue

    return results

def crawl_energy_news():
    return crawl_site("에너지신문", "https://www.energy-news.co.kr", 
                      "https://www.energy-news.co.kr/news/articleList.html?page={page}&view_type=sm")

def crawl_gas_news():
    return crawl_site("가스신문", "https://www.gasnews.com", 
                      "https://www.gasnews.com/news/articleList.html?page={page}&view_type=sm")

def crawl_electric_news():
    return crawl_site("전기신문", "https://www.electimes.com", 
                      "https://www.electimes.com/news/articleList.html?page={page}&view_type=sm")


# ==========================================
# 4. 실행: 크롤링 + latest.json 저장
# ==========================================

def job():
    print(f"\n[크롤링 시작] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    all_data = []
    all_data.extend(crawl_energy_news())
    all_data.extend(crawl_gas_news())
    all_data.extend(crawl_electric_news())

    dedup = {}
    for art in all_data:
        dedup[art["url"]] = art
    unique_articles = list(dedup.values())
    unique_articles.sort(key=lambda x: x["is_important"], reverse=True)

    with LATEST_JSON_PATH.open("w", encoding="utf-8") as f:
        json.dump(unique_articles, f, ensure_ascii=False, indent=2)

    print(f"[완료] {len(unique_articles)}건 수집 → {LATEST_JSON_PATH}")

if __name__ == "__main__":
    job()
