import json
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

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
    "한수원", "두산퓨얼셀", 
    "HPS", "HPC", "REC", "RPS"
]

MAX_PAGES = 3

DATA_DIR = Path("data")
BY_DATE_DIR = DATA_DIR / "by_date"
DATA_DIR.mkdir(exist_ok=True)
BY_DATE_DIR.mkdir(exist_ok=True)

ALL_JSON_PATH = DATA_DIR / "all.json"       # 전체 누적(인덱스 검색용)
LATEST_JSON_PATH = DATA_DIR / "latest.json" # 인덱스 기본 표시용(최신 날짜만)

# 3개 신문 목록 URL(페이지 포함)
ENERGY_BASE = "https://www.energy-news.co.kr"
GAS_BASE = "https://www.gasnews.com"
ELECT_BASE = "https://www.electimes.com"

ENERGY_LIST = ENERGY_BASE + "/news/articleList.html?page={page}&view_type=sm"
GAS_LIST = GAS_BASE + "/news/articleList.html?page={page}&view_type=sm"
ELECT_LIST = ELECT_BASE + "/news/articleList.html?page={page}&view_type=sm"

TIMEOUT = 12

# ==========================================
# 2. 공통 유틸
# ==========================================

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def get_soup(url: str) -> BeautifulSoup | None:
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"[ERROR] GET 실패: {url} | {e}")
        return None

def parse_date(raw: str) -> str:
    """
    '2025.12.18 10:30', '2025.12.18', '2025-12-18', '12.18 10:30' 등 대응
    """
    raw = (raw or "").strip()
    if not raw:
        return datetime.now().strftime("%Y-%m-%d")

    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 연도 없는 형태
    year = datetime.now().year
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            return datetime.strptime(f"{year}.{raw}", fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return datetime.now().strftime("%Y-%m-%d")

def make_tags(text: str) -> list[str]:
    low = (text or "").lower()
    tags = [kw for kw in KEYWORDS if kw.lower() in low]
    # 중복 제거(순서 유지)
    seen = set()
    out = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out

def contains_keyword(text: str) -> bool:
    low = (text or "").lower()
    return any(kw.lower() in low for kw in KEYWORDS)

def split_sentences_ko(text: str) -> list[str]:
    """
    lookbehind 고정폭 오류 회피 + 한국어 '다.' 처리
    """
    if not text:
        return []
    cleaned = normalize_spaces(text)
    cleaned = cleaned.replace("다. ", "다.\n").replace("다.", "다.\n")
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    sents = []
    for p in parts:
        for seg in p.split("\n"):
            seg = seg.strip()
            if seg:
                sents.append(seg)
    return sents

def summarize_2lines(body: str) -> str:
    sents = split_sentences_ko(body)
    if not sents:
        return ""
    # 인덱스는 2줄 clamp라, 실제 subtitle은 줄바꿈 없이 한 줄로 넣는 게 안정적
    return normalize_spaces(" ".join(sents[:2]))

# ==========================================
# 3. 본문 추출 (신문별 fallback 포함)
# ==========================================

def extract_body(url: str) -> str:
    soup = get_soup(url)
    if not soup:
        return ""

    # CMS 공통 후보
    candidates = [
        "div#article-view-content-div",
        "div#articleBody",
        "div.article-body",
        "div.article-text",
        "article",
    ]
    body_el = None
    for sel in candidates:
        body_el = soup.select_one(sel)
        if body_el:
            break

    texts = []
    if body_el:
        for node in body_el.find_all(["p", "span", "div"], recursive=True):
            t = node.get_text(" ", strip=True)
            if t:
                texts.append(t)
    else:
        # 마지막 fallback: 전체 p
        for p in soup.select("p"):
            t = p.get_text(" ", strip=True)
            if t:
                texts.append(t)

    body = normalize_spaces(" ".join(texts))

    # 너무 짧으면(메뉴/푸터만 잡힌 경우) 빈값 처리
    if len(body) < 40:
        return ""
    return body

# ==========================================
# 4. 목록 파서(신문별: 선택자 여러 후보)
# ==========================================

def pick_first(el, selectors: list[str]):
    for s in selectors:
        found = el.select_one(s)
        if found:
            return found
    return None

def crawl_list_generic(list_url: str, base_url: str, source_name: str, max_pages: int = 3) -> list[dict]:
    """
    #section-list 기반 CMS형 기사목록(에너지/가스/전기 공통 가능)
    selector가 바뀌어도 후보를 넓게 잡아 생존성 높임
    """
    out = []
    for page in range(1, max_pages + 1):
        url = list_url.format(page=page)
        soup = get_soup(url)
        if not soup:
            continue

        # 후보 1) sm 뷰에서 자주 쓰는 구조
        items = soup.select("#section-list .type1 li")
        # 후보 2) 다른 타입
        if not items:
            items = soup.select("#section-list ul.type1 > li")
        if not items:
            items = soup.select("#section-list ul.type > li")
        if not items:
            items = soup.select("#section-list li")

        page_total = 0
        page_keep = 0

        for li in items:
            try:
                a = pick_first(li, [
                    "h2.titles a",
                    "h4.titles a",
                    "h4.titles a.replace-titles",
                    "a.replace-titles",
                    "a[href*='articleView.html']",
                ])
                if not a:
                    continue

                title = a.get_text(strip=True)
                href = a.get("href", "").strip()
                if not href:
                    continue
                link = href if href.startswith("http") else (base_url + href)

                date_el = pick_first(li, [
                    "em.info.dated",
                    "em.replace-date",
                    "span.byline span",
                ])
                raw_date = date_el.get_text(strip=True) if date_el else ""
                date = parse_date(raw_date)

                page_total += 1

                # 본문(상세)에서 키워드도 검사하려면 본문이 필요
                body = extract_body(link)

                # ✅ 관련성 판단 로직(중요)
                # - 제목에 키워드 있으면 본문 실패해도 통과
                # - 제목에 없으면 본문에서 키워드 있으면 통과
                if not (contains_keyword(title) or contains_keyword(body)):
                    continue

                tags = make_tags(title + " " + body)

                subtitle = summarize_2lines(body)
                # 본문이 비거나 요약이 빈 경우, 최소한 제목 기반으로라도 빈칸 방지
                if not subtitle:
                    # 목록에서 미리보기 문구가 있으면 사용
                    lead_el = pick_first(li, ["p.lead", "p.lead a.replace-read", "p.lead a", "p.lead"])
                    lead = normalize_spaces(lead_el.get_text(" ", strip=True) if lead_el else "")
                    subtitle = lead[:220] if lead else ""

                out.append({
                    "source": source_name,
                    "title": title,
                    "url": link,
                    "date": date,
                    "tags": tags,
                    "subtitle": subtitle,
                    "is_important": 1 if tags else 0,
                })
                page_keep += 1
            except Exception:
                continue

        print(f"   [{source_name}] page {page}: 목록 {page_total}건 중 {page_keep}건 통과 → {url}")

    return out

# ==========================================
# 5. 통합 저장 (all.json / by_date / latest.json)
# ==========================================

def load_existing_all() -> list[dict]:
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
        if not u:
            continue
        d[u] = it
    return list(d.values())

def write_by_date(all_items: list[dict]):
    # 날짜별로 파일 생성
    bucket = {}
    for it in all_items:
        dt = it.get("date") or "unknown"
        bucket.setdefault(dt, []).append(it)

    for dt, lst in bucket.items():
        path = BY_DATE_DIR / f"{dt}.json"
        path.write_text(json.dumps(lst, ensure_ascii=False, indent=2), encoding="utf-8")

def pick_latest_date(all_items: list[dict]) -> str | None:
    dates = sorted({it.get("date") for it in all_items if it.get("date")}, reverse=True)
    return dates[0] if dates else None

def make_latest(all_items: list[dict]) -> list[dict]:
    latest = pick_latest_date(all_items)
    if not latest:
        return []
    return [it for it in all_items if it.get("date") == latest]

def sort_articles(items: list[dict]) -> list[dict]:
    # 최신 날짜 우선, 중요도 우선, 같은 날짜면 소스/제목
    def key(it):
        return (
            it.get("date") or "",
            it.get("is_important", 0),
            it.get("source") or "",
            it.get("title") or "",
        )
    return sorted(items, key=key, reverse=True)

def job():
    print(f"\n[크롤링 시작] {now_str()}")

    new_items = []
    # 1) 에너지신문
    new_items += crawl_list_generic(ENERGY_LIST, ENERGY_BASE, "에너지신문", max_pages=MAX_PAGES)
    # 2) 가스신문
    new_items += crawl_list_generic(GAS_LIST, GAS_BASE, "가스신문", max_pages=MAX_PAGES)
    # 3) 전기신문
    new_items += crawl_list_generic(ELECT_LIST, ELECT_BASE, "전기신문", max_pages=MAX_PAGES)

    print(f"\n[수집 결과] 신규 {len(new_items)}건 (필터 통과 기준)\n")

    # 누적(all.json) 유지: 기존 + 신규 합치고 URL로 중복제거
    existing = load_existing_all()
    merged = dedup_by_url(existing + new_items)
    merged = sort_articles(merged)

    # all.json 저장
    ALL_JSON_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    # 날짜별 저장(by_date)
    write_by_date(merged)

    # latest.json 저장(최신 날짜만)
    latest_items = sort_articles(make_latest(merged))
    LATEST_JSON_PATH.write_text(json.dumps(latest_items, ensure_ascii=False, indent=2), encoding="utf-8")

    latest_date = pick_latest_date(merged)
    print(f"[저장 완료] all.json={len(merged)}건 | latest.json={len(latest_items)}건 | 최신날짜={latest_date}\n")

if __name__ == "__main__":
    job()
