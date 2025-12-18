import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
from pathlib import Path
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

MAX_PAGES = 3

DATA_DIR = Path("data")
DAILY_DIR = DATA_DIR / "daily"
DATA_DIR.mkdir(exist_ok=True)
DAILY_DIR.mkdir(parents=True, exist_ok=True)

MANIFEST_PATH = DATA_DIR / "manifest.json"

# 3개 신문 리스트 URL
ENERGY_BASE = "https://www.energy-news.co.kr"
GAS_BASE = "https://www.gasnews.com"
ELECT_BASE = "https://www.electimes.com"

ENERGY_LIST = ENERGY_BASE + "/news/articleList.html?page={page}&view_type=sm"
GAS_LIST    = GAS_BASE    + "/news/articleList.html?page={page}&view_type=sm"
ELECT_LIST  = ELECT_BASE  + "/news/articleList.html?page={page}&view_type=sm"

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ==========================================
# 2. 유틸
# ==========================================

def get_soup(url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        return BeautifulSoup(res.text, "html.parser")
    except Exception as e:
        print(f"[ERROR] {url} → {e}")
        return None

def contains_keyword(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k.lower() in t for k in KEYWORDS)

def make_tags(text: str):
    if not text:
        return []
    t = text.lower()
    tags = [k for k in KEYWORDS if k.lower() in t]
    # 중복 제거(순서 유지)
    seen = set()
    out = []
    for x in tags:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out

def normalize_date_common(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()

    # 2025.12.10 09:30 / 2025.12.10 / 2025-12-10 / 2025-12-10T...
    # ISO 형태도 일부 대응
    iso = raw.replace("T", " ").split("+")[0].split("Z")[0].strip()

    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(iso, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 연도 없는 12.10 09:30 / 12.10 형태
    year = datetime.now().year
    try:
        return datetime.strptime(f"{year}.{raw}", "%Y.%m.%d %H:%M").strftime("%Y-%m-%d")
    except Exception:
        try:
            return datetime.strptime(f"{year}.{raw}", "%Y.%m.%d").strftime("%Y-%m-%d")
        except Exception:
            return ""

# ==========================================
# 3. 기사 상세: 날짜/본문/요약
# ==========================================

def extract_published_date_from_article(soup: BeautifulSoup) -> str:
    """상세페이지에서 발행일을 최대한 정확히 추출"""
    # 1) OpenGraph / meta published_time
    meta_candidates = [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"name": "article:published_time"}),
        ("meta", {"property": "og:article:published_time"}),
        ("meta", {"name": "pubdate"}),
        ("meta", {"name": "publication_date"}),
        ("meta", {"itemprop": "datePublished"}),
    ]
    for tag, attrs in meta_candidates:
        m = soup.find(tag, attrs=attrs)
        if m and m.get("content"):
            d = normalize_date_common(m["content"])
            if d:
                return d

    # 2) time 태그
    time_tag = soup.find("time")
    if time_tag:
        dt = time_tag.get("datetime") or time_tag.get_text(strip=True)
        d = normalize_date_common(dt)
        if d:
            return d

    # 3) 흔한 날짜 표시 클래스들
    date_text_candidates = []
    for sel in [
        "em.info.dated", "span.dated", "p.dated", ".article-datetime", ".byline", ".view-dated", ".date"
    ]:
        el = soup.select_one(sel)
        if el:
            date_text_candidates.append(el.get_text(" ", strip=True))
    for raw in date_text_candidates:
        d = normalize_date_common(raw)
        if d:
            return d

    return ""  # 못 찾으면 빈값

def extract_article_body(soup: BeautifulSoup) -> str:
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
    if not text:
        return []
    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = cleaned.replace("다. ", "다.\n").replace("다.", "다.\n")
    parts = re.split(r"(?<=[.!?])\s+", cleaned)

    sentences = []
    for p in parts:
        for seg in p.split("\n"):
            seg = seg.strip()
            if seg:
                sentences.append(seg)
    return sentences

def summarize_body_2lines(body: str) -> str:
    sents = split_sentences(body)
    if not sents:
        return ""
    # 2문장 + 화면에서는 2줄 clamp이므로 줄바꿈 대신 공백 처리
    return " ".join(sents[:2]).strip()

def fetch_article_detail(url: str):
    soup = get_soup(url)
    if not soup:
        return "", "", ""
    pub_date = extract_published_date_from_article(soup)
    body = extract_article_body(soup)
    subtitle = summarize_body_2lines(body)
    return pub_date, body, subtitle

# ==========================================
# 4. 리스트 크롤러 (1~3페이지)
# ==========================================

def crawl_list(source_name: str, list_url_tmpl: str, base_url: str):
    """
    공통 리스트 파서(요약형 CMS 계열 대응)
    리턴: [{source,title,url,listed_date_raw}, ...]
    """
    items = []
    for page in range(1, MAX_PAGES + 1):
        url = list_url_tmpl.format(page=page)
        print(f"   [{source_name}] {page}페이지 → {url}")
        soup = get_soup(url)
        if not soup:
            continue

        # CMS별 selector 약간씩 다름: h2.titles a 또는 h4.titles a
        candidates = soup.select("#section-list .type1 li")
        if not candidates:
            # 전기신문/기타 변형 대비
            candidates = soup.select("#section-list li")

        for li in candidates:
            a = li.select_one("h2.titles a") or li.select_one("h4.titles a") or li.select_one("a")
            if not a:
                continue

            title = a.get_text(strip=True)
            href = a.get("href", "")
            if not href:
                continue
            full = href if href.startswith("http") else base_url + href

            date_el = li.select_one("em.info.dated")
            listed_raw = date_el.get_text(strip=True) if date_el else ""

            items.append({
                "source": source_name,
                "title": title,
                "url": full,
                "listed_raw": listed_raw
            })
    return items

# ==========================================
# 5. 통합 실행: 날짜별 JSON 생성 + manifest 생성
# ==========================================

def run():
    print(f"\n[RUN] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    all_listed = []
    all_listed.extend(crawl_list("에너지신문", ENERGY_LIST, ENERGY_BASE))
    all_listed.extend(crawl_list("가스신문",   GAS_LIST,    GAS_BASE))
    all_listed.extend(crawl_list("전기신문",   ELECT_LIST,  ELECT_BASE))

    # URL 중복 제거(리스트 단계)
    dedup_list = {}
    for it in all_listed:
        dedup_list[it["url"]] = it
    unique_listed = list(dedup_list.values())

    print(f"[INFO] 리스트 수집(중복제거 후): {len(unique_listed)}건")

    # 상세 조회 + 키워드 필터(제목+본문 일부)
    articles = []
    for it in unique_listed:
        title = it["title"]
        url = it["url"]

        pub_date, body, subtitle = fetch_article_detail(url)

        # 날짜 fallback: 상세에서 못 찾으면 리스트 날짜로
        if not pub_date:
            pub_date = normalize_date_common(it.get("listed_raw", ""))

        # 그래도 없으면 오늘로 넣되, 이 경우는 후처리에서 걸러지게 가능
        if not pub_date:
            pub_date = datetime.now().strftime("%Y-%m-%d")

        # 키워드 판단(제목 + 본문 앞부분)
        probe_text = f"{title} {body[:1500]}"  # 너무 길게는 X
        if not contains_keyword(probe_text):
            continue

        tags = make_tags(probe_text)

        articles.append({
            "title": title,
            "subtitle": subtitle,
            "date": pub_date,
            "source": it["source"],
            "url": url,
            "tags": tags
        })

    # 날짜별 그룹핑
    by_date = {}
    for a in articles:
        by_date.setdefault(a["date"], []).append(a)

    # 각 날짜 파일 저장(정렬: 중요도(태그수) + 제목)
    saved_dates = []
    for d, arr in by_date.items():
        arr.sort(key=lambda x: (len(x.get("tags", []))), reverse=True)
        out_path = DAILY_DIR / f"{d}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(arr, f, ensure_ascii=False, indent=2)
        saved_dates.append(d)

    # manifest 생성(날짜 목록 + 최신일)
    saved_dates = sorted(set(saved_dates))
    manifest = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dates": saved_dates,
        "latest": saved_dates[-1] if saved_dates else ""
    }
    with MANIFEST_PATH.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"[DONE] 날짜별 저장: {len(saved_dates)}일 / manifest.json 생성 완료")

if __name__ == "__main__":
    run()
