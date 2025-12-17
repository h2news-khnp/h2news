    import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
from pathlib import Path
import re

# ==========================================
# 0. 경로 설정 (실행 위치와 무관하게 repo/data/latest.json에 생성)
#    - 파일 위치: data/crawler/news_crawler.py 라고 가정
#    - BASE_DIR  : repo 루트
# ==========================================

BASE_DIR = Path(__file__).resolve().parent.parent   # repo 기준(= data/ 상위)
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

LATEST_JSON_PATH = DATA_DIR / "latest.json"

# ==========================================
# 1. 설정
# ==========================================

KEYWORDS = [
    "수소", "연료전지", "그린수소", "청정수소", "블루수소", "핑크수소",
    "PAFC", "SOFC", "MCFC", "PEM",
    "수전해", "전해조", "PEMEC", "AEM", "알카라인",
    "암모니아", "암모니아크래킹", "CCU", "CCUS",
    "수소생산", "수소저장", "액화수소", "충전소", "수소차", "수소버스",
    "한수원", "두산퓨얼셀", "한화임팩트", "현대차",
    "REC", "RPS", "PPA", "ESS"
]

MAX_PAGES = 3
TIMEOUT = 12

# 3개 신문 리스트 URL (요약형 view_type=sm 사용)
SOURCES = [
    {
        "name": "에너지신문",
        "base": "https://www.energy-news.co.kr",
        "list_url": "https://www.energy-news.co.kr/news/articleList.html?page={page}&view_type=sm",
        "list_item_selector": "#section-list .type1 li",
        "title_selector_candidates": ["h2.titles a", "h4.titles a"],
        "date_selector_candidates": ["em.info.dated", "span.date", "li span.date"],
    },
    {
        "name": "가스신문",
        "base": "https://www.gasnews.com",
        "list_url": "https://www.gasnews.com/news/articleList.html?page={page}&view_type=sm",
        "list_item_selector": "#section-list .type1 li",
        "title_selector_candidates": ["h2.titles a", "h4.titles a"],
        "date_selector_candidates": ["em.info.dated", "span.date", "li span.date"],
    },
    {
        "name": "전기신문",
        "base": "https://www.electimes.com",
        "list_url": "https://www.electimes.com/news/articleList.html?page={page}&view_type=sm",
        "list_item_selector": "#section-list .type1 li",
        "title_selector_candidates": ["h2.titles a", "h4.titles a"],
        "date_selector_candidates": ["em.info.dated", "span.date", "li span.date"],
    },
]

# ==========================================
# 2. 공통 유틸
# ==========================================

def get_soup(url: str):
    try:
        res = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=TIMEOUT
        )
        res.raise_for_status()
        return BeautifulSoup(res.text, "html.parser")
    except Exception as e:
        print(f"[ERROR] GET 실패: {url} / {e}")
        return None


def to_abs_url(base: str, href: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return base + href
    return base + "/" + href


def normalize_date(raw: str) -> str:
    """
    다양한 형식 대응:
    - '2025.12.10', '2025.12.10 09:30', '2025-12-10', '12.10 09:30', '12.10'
    """
    if not raw:
        return datetime.now().strftime("%Y-%m-%d")

    raw = raw.strip()

    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except:
            pass

    # '12.10 09:30' / '12.10' 형태
    year = datetime.now().year
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            return datetime.strptime(f"{year}.{raw}", fmt).strftime("%Y-%m-%d")
        except:
            pass

    return datetime.now().strftime("%Y-%m-%d")


def find_keywords(text: str) -> list[str]:
    if not text:
        return []
    lower = text.lower()
    return [k for k in KEYWORDS if k.lower() in lower]


def extract_article_body(url: str) -> str:
    """3개 신문 공통 본문 영역 후보 대응 + fallback(p 전체)"""
    soup = get_soup(url)
    if not soup:
        return ""

    # 많이 쓰는 본문 컨테이너 후보들
    body_el = soup.select_one(
        "div#article-view-content-div, "
        "div#articleBody, "
        "div.article-body, "
        "div.article-text, "
        "article .article-body, "
        "div[itemprop='articleBody']"
    )

    if body_el:
        texts = [p.get_text(" ", strip=True) for p in body_el.find_all("p")]
        body = " ".join(texts).strip()
    else:
        # fallback: p 전체에서 너무 짧은 p는 제외
        ps = [p.get_text(" ", strip=True) for p in soup.select("p")]
        ps = [t for t in ps if len(t) >= 30]
        body = " ".join(ps[:20]).strip()

    body = re.sub(r"\s+", " ", body)
    return body


def summarize_2_sentences(text: str) -> str:
    """본문에서 앞부분 2문장 뽑기 (subtitle로 사용)"""
    if not text:
        return ""

    cleaned = re.sub(r"\s+", " ", text).strip()

    # 한국어 종결 '다.' 기준 보조 분리
    cleaned = cleaned.replace("다. ", "다.\n").replace("다.", "다.\n")

    parts = []
    for chunk in cleaned.split("\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        # 영어권 문장부호 기준 분리
        segs = re.split(r"(?<=[.!?])\s+", chunk)
        parts.extend([s.strip() for s in segs if s.strip()])

    if not parts:
        return cleaned[:160]

    return " ".join(parts[:2])


def pick_first(selector_candidates: list[str], root):
    for sel in selector_candidates:
        el = root.select_one(sel)
        if el:
            return el
    return None

# ==========================================
# 3. 신문별 크롤러 (1~3페이지)
#    - 제목 + 본문에 키워드가 하나라도 있으면 포함
#    - tags는 제목/본문에서 발견된 키워드 합집합
# ==========================================

def crawl_source(conf: dict) -> list[dict]:
    name = conf["name"]
    base = conf["base"]
    list_url_tpl = conf["list_url"]

    results = []

    for page in range(1, MAX_PAGES + 1):
        url = list_url_tpl.format(page=page)
        print(f"[{name}] {page}페이지 → {url}")

        soup = get_soup(url)
        if not soup:
            continue

        items = soup.select(conf["list_item_selector"])
        if not items:
            print(f"[WARN] {name} {page}페이지: 리스트 항목을 못 찾음(선택자 확인 필요)")
            continue

        for li in items:
            try:
                title_a = pick_first(conf["title_selector_candidates"], li)
                if not title_a:
                    continue

                title = title_a.get_text(strip=True)
                href = title_a.get("href", "")
                article_url = to_abs_url(base, href)
                if not article_url:
                    continue

                date_el = pick_first(conf["date_selector_candidates"], li)
                raw_date = date_el.get_text(strip=True) if date_el else ""
                date = normalize_date(raw_date)

                # 본문 추출
                body = extract_article_body(article_url)

                # 키워드 판단: 제목 + 본문
                tags = list(dict.fromkeys(find_keywords(title) + find_keywords(body)))
                if not tags:
                    continue

                subtitle = summarize_2_sentences(body)

                results.append({
                    "title": title,
                    "subtitle": subtitle,
                    "date": date,
                    "source": name,
                    "url": article_url,
                    "tags": tags,
                })
            except Exception:
                continue

    return results

# ==========================================
# 4. 통합 실행 + latest.json 저장 (index.html 호환)
#    - 중복 제거: url 기준
# ==========================================

def job():
    print(f"\n[START] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    all_articles = []
    for conf in SOURCES:
        all_articles.extend(crawl_source(conf))

    # url 기준 중복 제거
    dedup = {a["url"]: a for a in all_articles}
    final = list(dedup.values())

    # 정렬: 최신 날짜 우선(문자열 yyyy-mm-dd라 정렬 가능)
    final.sort(key=lambda x: (x["date"], x["source"]), reverse=True)

    with LATEST_JSON_PATH.open("w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    print(f"[OK] {len(final)}건 저장 완료 → {LATEST_JSON_PATH}")

# ==========================================
# 5. 메인: 호출될 때 한 번만 실행
# ==========================================

if __name__ == "__main__":
    job()                        
                
