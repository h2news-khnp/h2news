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


def check_keywords(title: str):
    """제목에 포함된 키워드를 태그로 리턴"""
    lower = title.lower()
    return [kw for kw in KEYWORDS if kw.lower() in lower]


def normalize_date_common(raw: str):
    """
    여러 신문 공통 날짜 파서
    '2025.12.10', '2025.12.10 09:30', '2025-12-10', '12.10 09:30' 등 대응
    """
    if not raw:
        return datetime.now().strftime("%Y-%m-%d")

    raw = raw.strip()

    # 연도까지 있는 경우
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 연도가 없는 케이스
    year = datetime.now().year
    try:
        return datetime.strptime(f"{year}.{raw}", "%Y.%m.%d %H:%M").strftime("%Y-%m-%d")
    except Exception:
        try:
            return datetime.strptime(f"{year}.{raw}", "%Y.%m.%d").strftime("%Y-%m-%d")
        except Exception:
            return datetime.now().strftime("%Y-%m-%d")


# ==========================================
# 3. 본문 추출 & 요약 (1 / 2 / 3줄)
# ==========================================

def extract_article_body(url: str) -> str:
    """기사 상세 본문 텍스트 추출 (3개 신문 공통 대응)"""
    soup = get_soup(url)
    if not soup:
        return ""

    body_el = soup.select_one(
        "div#article-view-content-div, "
        "div.article-body, "
        "div#articleBody, "
        "div.article-text"
    )
    if not body_el:
        texts = [p.get_text(" ", strip=True) for p in soup.select("p")]
    else:
        texts = [x.get_text(" ", strip=True) for x in body_el.find_all(["p", "span", "div"])]

    body = " ".join(texts)
    body = re.sub(r"\s+", " ", body).strip()
    return body


def split_sentences(text: str):
    """lookbehind 문제 없는 한국어 + 영어 혼합 문장 분리"""
    if not text:
        return []

    cleaned = re.sub(r"\s+", " ", text).strip()

    # '다.' 기준으로 줄바꿈
    cleaned = cleaned.replace("다. ", "다.\n")
    cleaned = cleaned.replace("다.", "다.\n")

    # 영어권 문장부호 기준 분리
    parts = re.split(r"(?<=[.!?])\s+", cleaned)

    sentences = []
    for p in parts:
        for seg in p.split("\n"):
            seg = seg.strip()
            if seg:
                sentences.append(seg)

    return sentences


def summarize_variants(body: str):
    """
    본문에서
      - 1줄 요약: 첫 문장
      - 2줄 요약: 앞 2문장
      - 3줄 요약: 앞 3문장
    을 만들어서 dict로 반환
    """
    sents = split_sentences(body)
    if not sents:
        return {"one": "", "two": "", "three": ""}

    one = sents[0]
    two = " ".join(sents[:2]) if len(sents) >= 2 else one
    three = " ".join(sents[:3]) if len(sents) >= 3 else two

    # index.html에서 한 줄로 보여주기 위해 개행 제거
    return {
        "one": one.replace("\n", " "),
        "two": two.replace("\n", " "),
        "three": three.replace("\n", " "),
    }


# ==========================================
# 4. 각 신문별 크롤러
#    👉 수정 포인트: tags가 비어 있으면 그 기사는 버림
# ==========================================

def crawl_energy_news():
    """에너지신문"""
    print("   [에너지신문] 크롤링 시작...")
    results = []
    base_url = "https://www.energy-news.co.kr"
    url = f"{base_url}/news/articleList.html?view_type=sm"

    soup = get_soup(url)
    if not soup:
        return results

    articles = soup.select("#section-list .type1 li")
    for art in articles:
        try:
            title_tag = art.select_one("h2.titles a")
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            link = title_tag["href"]
            if not link.startswith("http"):
                link = base_url + link

            # 🔹 제목에서 키워드 태그 생성
            tags = check_keywords(title)
            # 🔹 수소 관련 키워드가 하나도 없으면 패스
            if not tags:
                continue

            date_tag = art.select_one("em.info.dated")
            raw_date = date_tag.get_text(strip=True) if date_tag else ""
            date = normalize_date_common(raw_date)

            body = extract_article_body(link)
            summaries = summarize_variants(body)

            results.append({
                "source": "에너지신문",
                "title": title,
                "url": link,
                "date": date,
                "tags": tags,                  # 최소 1개 이상 보장
                "summary1": summaries["one"],  # 1줄 요약
                "subtitle": summaries["two"],  # 2줄 요약(기본)
                "summary3": summaries["three"],# 3줄 요약
                "is_important": True,          # 태그가 있으므로 True
            })
        except Exception:
            continue

    return results


def crawl_gas_news():
    """가스신문"""
    print("   [가스신문] 크롤링 시작...")
    results = []
    base_url = "https://www.gasnews.com"
    url = f"{base_url}/news/articleList.html?view_type=sm"

    soup = get_soup(url)
    if not soup:
        return results

    articles = soup.select("#section-list .type1 li")
    if not articles:
        articles = soup.select(".article-list .list-block")

    for art in articles:
        try:
            title_tag = art.select_one("h2.titles a") or art.select_one("h4.titles a")
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            link = title_tag["href"]
            if not link.startswith("http"):
                link = base_url + link

            # 🔹 키워드 체크
            tags = check_keywords(title)
            if not tags:
                continue

            date_tag = art.select_one("em.info.dated")
            raw_date = date_tag.get_text(strip=True) if date_tag else ""
            date = normalize_date_common(raw_date)

            body = extract_article_body(link)
            summaries = summarize_variants(body)

            results.append({
                "source": "가스신문",
                "title": title,
                "url": link,
                "date": date,
                "tags": tags,
                "summary1": summaries["one"],
                "subtitle": summaries["two"],
                "summary3": summaries["three"],
                "is_important": True,
            })
        except Exception:
            continue

    return results


def crawl_electric_news():
    """전기신문"""
    print("   [전기신문] 크롤링 시작...")
    results = []
    base_url = "https://www.electimes.com"
    url = f"{base_url}/news/articleList.html?view_type=sm"

    soup = get_soup(url)
    if not soup:
        return results

    articles = soup.select("#section-list .type1 li")
    for art in articles:
        try:
            title_tag = art.select_one("h2.titles a") or art.select_one("h4.titles a")
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            link = title_tag["href"]
            if not link.startswith("http"):
                link = base_url + link

            # 🔹 키워드 체크
            tags = check_keywords(title)
            if not tags:
                continue

            date_tag = art.select_one("em.info.dated")
            raw_date = date_tag.get_text(strip=True) if date_tag else ""
            date = normalize_date_common(raw_date)

            body = extract_article_body(link)
            summaries = summarize_variants(body)

            results.append({
                "source": "전기신문",
                "title": title,
                "url": link,
                "date": date,
                "tags": tags,
                "summary1": summaries["one"],
                "subtitle": summaries["two"],
                "summary3": summaries["three"],
                "is_important": True,
            })
        except Exception:
            continue

    return results


# ==========================================
# 5. 통합 실행 + latest.json 저장
# ==========================================

def job():
    print(f"\n[크롤링 시작] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    all_data = []
    all_data.extend(crawl_energy_news())
    all_data.extend(crawl_gas_news())
    all_data.extend(crawl_electric_news())

    # URL 기준 중복 제거
    dedup = {}
    for art in all_data:
        dedup[art["url"]] = art
    unique_articles = list(dedup.values())

    # 오늘 날짜 기사만 남기기
    today = datetime.now().strftime("%Y-%m-%d")
    unique_articles = [a for a in unique_articles if a["date"] == today]

    # 이미 is_important = True로 고정이지만, 혹시 확장 대비 정렬 유지
    unique_articles.sort(key=lambda x: x["is_important"], reverse=True)

    with LATEST_JSON_PATH.open("w", encoding="utf-8") as f:
        json.dump(unique_articles, f, ensure_ascii=False, indent=2)

    print(f"[완료] {len(unique_articles)}건 수집 → {LATEST_JSON_PATH}")


# ==========================================
# 6. 메인
# ==========================================

if __name__ == "__main__":
    job()
