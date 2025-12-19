import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

# ==========================================
# 1. 설정
# ==========================================

KST = ZoneInfo("Asia/Seoul")
TIMEOUT = 15
MAX_PAGES = 3
DEBUG = True  # 안정화되면 False 권장

KEYWORDS = [
    "수소", "연료전지", "그린수소", "청정수소", "블루수소", "원자력",
    "PAFC", "SOFC", "MCFC", "PEM", "재생", "배출권", "히트펌프", "도시가스", "구역전기", "PPA",
    "수전해", "전해조", "PEMEC", "AEM", "알카라인", "분산", "NDC", "핑크수소",
    "암모니아", "암모니아크래킹", "CCU", "CCUS", "기후부", "ESS", "배터리",
    "수소생산", "수소저장", "액화수소",
    "충전소", "수소버스", "수소차",
    "한수원", "두산퓨얼셀", "한화임팩트", "현대차",
    "HPS", "HPC", "REC", "RPS"
]

DATA_DIR = Path("data")
BY_DATE_DIR = DATA_DIR / "by_date"
DATA_DIR.mkdir(exist_ok=True)
BY_DATE_DIR.mkdir(exist_ok=True)

ALL_JSON_PATH = DATA_DIR / "all.json"
LATEST_JSON_PATH = DATA_DIR / "latest.json"

ENERGY_BASE = "https://www.energy-news.co.kr"
GAS_BASE = "https://www.gasnews.com"
ELECT_BASE = "https://www.electimes.com"

ENERGY_LIST = ENERGY_BASE + "/news/articleList.html?page={page}&view_type=sm"
GAS_LIST = GAS_BASE + "/news/articleList.html?page={page}&view_type=sm"
ELECT_LIST = ELECT_BASE + "/news/articleList.html?page={page}&view_type=sm"


# ==========================================
# 2. 공통 유틸
# ==========================================

def kst_now():
    return datetime.now(KST)

def today_kst_str():
    return kst_now().strftime("%Y-%m-%d")

def now_str():
    return kst_now().strftime("%Y-%m-%d %H:%M:%S")

def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()

def get_soup(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    }
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"[ERROR] GET 실패: {url} → {e}")
        return None

def contains_keyword(text: str) -> bool:
    low = (text or "").lower()
    return any(k.lower() in low for k in KEYWORDS)

def make_tags(text: str) -> list[str]:
    low = (text or "").lower()
    seen = set()
    out = []
    for k in KEYWORDS:
        kk = k.lower()
        if kk in low and k not in seen:
            seen.add(k)
            out.append(k)
    return out

def parse_date_flexible(raw: str) -> str | None:
    """
    '2025.12.19 10:30', '2025.12.19', '2025-12-19', '12.19 10:30' 등 대응
    """
    raw = (raw or "").strip()
    if not raw:
        return None

    # full year
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d", "%Y-%m-%d", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # no year (assume current year in KST)
    year = kst_now().year
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            return datetime.strptime(f"{year}.{raw}", fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


# ==========================================
# 3. 전기신문 잡음 제거 (강화)
# ==========================================

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

def clean_electimes_noise(text: str) -> str:
    s = normalize_spaces(text)

    # 이메일 제거
    s = EMAIL_RE.sub(" ", s)

    # 기자명/기자 표시 제거(예: 홍길동 기자)
    s = re.sub(r"[가-힣]{2,4}\s*기자", " ", s)

    # 제보/공유/SNS/저작권 등 문구 제거
    noise = [
        r"제보", r"기사\s*보내기", r"기사보내기", r"공유", r"SNS", r"트위터", r"페이스북",
        r"카카오톡", r"밴드", r"구독", r"좋아요",
        r"무단전재\s*및\s*재배포\s*금지", r"저작권", r"Copyright",
        r"electimes", r"전기신문"
    ]
    for pat in noise:
        s = re.sub(pat, " ", s, flags=re.IGNORECASE)

    # 너무 흔한 “연락처/메일/제보” 관련 문장 패턴 제거(줄 단위 효과를 내기 위해 구두점 기준도 정리)
    s = re.sub(r"\b(제보|문의|연락|메일|e-?mail)\b[^.。!?]*", " ", s, flags=re.IGNORECASE)

    return normalize_spaces(s)

def clean_common_noise(text: str) -> str:
    s = normalize_spaces(text)
    s = re.sub(r"무단전재\s*및\s*재배포\s*금지", " ", s)
    s = EMAIL_RE.sub(" ", s)
    return normalize_spaces(s)

def split_sentences_ko(text: str) -> list[str]:
    if not text:
        return []
    s = normalize_spaces(text)

    # 한국어 '다.' 기준 줄 경계 + 영문 구두점
    s = s.replace("다. ", "다.\n").replace("다.", "다.\n")
    parts = re.split(r"(?<=[.!?])\s+", s)

    out = []
    for p in parts:
        for seg in p.split("\n"):
            seg = seg.strip()
            if seg:
                out.append(seg)
    return out

def summarize_2lines(body: str) -> str:
    sents = split_sentences_ko(body)
    if not sents:
        return ""
    return normalize_spaces(" ".join(sents[:2]))


# ==========================================
# 4. 기사 상세에서 발행일/본문 추출 (핵심)
# ==========================================

def extract_published_date_from_article(soup: BeautifulSoup) -> str | None:
    """
    목록 날짜가 틀리는 경우가 있어, 상세 페이지에서 발행일을 최우선으로 재확인.
    """
    # 1) og/article meta
    meta_candidates = [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"name": "article:published_time"}),
        ("meta", {"property": "og:updated_time"}),
        ("meta", {"name": "og:updated_time"}),
    ]
    for tag, attrs in meta_candidates:
        m = soup.find(tag, attrs=attrs)
        if m and m.get("content"):
            content = m.get("content").strip()
            # ISO 8601 like 2025-12-19T08:10:00+09:00
            m2 = re.search(r"(\d{4}-\d{2}-\d{2})", content)
            if m2:
                return m2.group(1)

    # 2) 흔한 날짜 표기 영역(신문별 약간 다름)
    # (정확한 셀렉터가 바뀌어도 버티도록 후보를 넓힘)
    sel_candidates = [
        "span.updated", "span.published", "span.date", "em.info.dated", "li.date", "p.date",
        "div.article-head em", "div.article-head span",
        "div.view-head em", "div.view-head span",
    ]
    for sel in sel_candidates:
        el = soup.select_one(sel)
        if el:
            dt = parse_date_flexible(el.get_text(" ", strip=True))
            if dt:
                return dt

    # 3) 본문 내 패턴(YYYY.MM.DD / YYYY-MM-DD)
    text = soup.get_text(" ", strip=True)
    m3 = re.search(r"(\d{4}[.-]\d{2}[.-]\d{2})", text)
    if m3:
        dt = parse_date_flexible(m3.group(1).replace("-", "."))
        if dt:
            return dt

    return None

def extract_body_from_article(url: str, source: str) -> tuple[str, str | None]:
    soup = get_soup(url)
    if not soup:
        return "", None

    published = extract_published_date_from_article(soup)

    # 본문 후보 셀렉터(국내 기사 CMS 공통)
    selectors = [
        "div#article-view-content-div",   # 한국지역/에너지신문 계열 자주
        "div#articleBody",
        "div.article-body",
        "div.article-text",
        "article",
        "div#articleBodyContents",
    ]

    body_el = None
    for sel in selectors:
        body_el = soup.select_one(sel)
        if body_el:
            break

    texts = []
    if body_el:
        for t in body_el.find_all(["p", "span", "div"], recursive=True):
            txt = t.get_text(" ", strip=True)
            if txt:
                texts.append(txt)
    else:
        for p in soup.select("p"):
            txt = p.get_text(" ", strip=True)
            if txt:
                texts.append(txt)

    body = normalize_spaces(" ".join(texts))

    # 신문별 정제
    body = clean_common_noise(body)
    if source == "전기신문":
        body = clean_electimes_noise(body)

    if len(body) < 60:
        # 너무 짧으면 본문 추출 실패 가능 → 빈값 처리
        return "", published

    return body, published


# ==========================================
# 5. 목록 크롤러 (1~3페이지)
#    - 제목 키워드 OR 본문 키워드 통과
#    - 상세 발행일 우선 적용
# ==========================================

def crawl_list(list_url: str, base_url: str, source: str) -> list[dict]:
    results = []
    for page in range(1, MAX_PAGES + 1):
        page_url = list_url.format(page=page)
        soup = get_soup(page_url)
        if not soup:
            continue

        # 잡음 최소화를 위해 type1 우선
        items = soup.select("#section-list .type1 li")
        if not items:
            items = soup.select("#section-list li")

        kept = 0
        total = 0

        for li in items:
            try:
                a = li.select_one("h2.titles a, h4.titles a, a.replace-titles, a[href*='articleView.html']")
                if not a:
                    continue

                title = a.get_text(strip=True)
                href = (a.get("href", "") or "").strip()
                if not href:
                    continue
                url = href if href.startswith("http") else base_url + href

                total += 1

                # 상세 본문/발행일
                body, pub_date = extract_body_from_article(url, source)

                # 관련성 판단: 제목 또는 본문
                if not (contains_keyword(title) or contains_keyword(body)):
                    continue

                tags = make_tags(title + " " + body)
                subtitle = summarize_2lines(body)

                # 날짜: 상세 발행일 우선, 없으면 목록 날짜
                list_date_el = li.select_one("em.info.dated, em.replace-date, span.byline span")
                list_date = parse_date_flexible(list_date_el.get_text(" ", strip=True) if list_date_el else "")
                date = pub_date or list_date or today_kst_str()

                results.append({
                    "source": source,
                    "title": title,
                    "url": url,
                    "date": date,
                    "tags": tags,
                    "subtitle": subtitle,
                    "is_important": 1 if tags else 0,
                })
                kept += 1

            except Exception as e:
                if DEBUG:
                    print(f"[WARN] {source} 항목 스킵: {e}")
                continue

        print(f"[{source}] page {page} → {kept}건 / 목록 {total}개 | {page_url}")

    return results


# ==========================================
# 6. 저장 로직
#    - all.json: 누적(중복 URL 제거)
#    - by_date: 날짜별 파일
#    - latest.json: '당일(KST)' 기사만
# ==========================================

def load_all_existing() -> list[dict]:
    if ALL_JSON_PATH.exists():
        try:
            return json.loads(ALL_JSON_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def dedup_by_url(items: list[dict]) -> list[dict]:
    d = {}
    for it in items:
        u = it.get("url")
        if u:
            d[u] = it
    return list(d.values())

def sort_articles(items: list[dict]) -> list[dict]:
    # 최신 날짜, 중요도, 소스 순
    return sorted(
        items,
        key=lambda x: (x.get("date", ""), x.get("is_important", 0), x.get("source", ""), x.get("title", "")),
        reverse=True
    )

def write_by_date(items: list[dict]) -> dict[str, list[dict]]:
    bucket: dict[str, list[dict]] = {}
    for it in items:
        d = it.get("date") or "unknown"
        bucket.setdefault(d, []).append(it)

    for d, lst in bucket.items():
        (BY_DATE_DIR / f"{d}.json").write_text(
            json.dumps(sort_articles(lst), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    return bucket

def job():
    print(f"\n[크롤링 시작] {now_str()} (KST today={today_kst_str()})")

    new_items = []
    new_items += crawl_list(ENERGY_LIST, ENERGY_BASE, "에너지신문")
    new_items += crawl_list(GAS_LIST, GAS_BASE, "가스신문")
    new_items += crawl_list(ELECT_LIST, ELECT_BASE, "전기신문")

    print(f"\n[신규 수집] {len(new_items)}건\n")

    # 누적(all.json) = 기존 + 신규, URL 기준 dedup
    existing = load_all_existing()
    merged = dedup_by_url(existing + new_items)
    merged = sort_articles(merged)

    # all.json 저장 (누적)
    ALL_JSON_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    # 날짜별 저장
    by_date = write_by_date(merged)

    # ✅ latest.json은 "당일(KST)"만
    today = today_kst_str()
    latest_items = sort_articles(by_date.get(today, []))
    LATEST_JSON_PATH.write_text(json.dumps(latest_items, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[저장 완료] all.json={len(merged)}건 | by_date={len(by_date)}일 | latest(today)={len(latest_items)}건")

if __name__ == "__main__":
    job()
