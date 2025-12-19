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
    "충전소", "수소버스", "수소차",
    "한수원", "두산퓨얼셀",
    "HPS", "REC", "RPS"
]

MAX_PAGES = 3
TIMEOUT = 12

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

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()

def get_soup(url: str):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=TIMEOUT)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"[ERROR] {url} → {e}")
        return None

def parse_date(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return datetime.now().strftime("%Y-%m-%d")

    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    year = datetime.now().year
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            return datetime.strptime(f"{year}.{raw}", fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return datetime.now().strftime("%Y-%m-%d")

def contains_keyword(text: str) -> bool:
    low = (text or "").lower()
    return any(k.lower() in low for k in KEYWORDS)

def make_tags(text: str) -> list:
    low = (text or "").lower()
    seen = set()
    tags = []
    for k in KEYWORDS:
        if k.lower() in low and k not in seen:
            tags.append(k)
            seen.add(k)
    return tags

def split_sentences_ko(text: str) -> list[str]:
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
    return normalize_spaces(" ".join(sents[:2]))

# ==========================================
# 3. 전기신문/에너지신문/가스신문 잡음 제거
# ==========================================

def clean_electimes_noise(text: str) -> str:
    """
    전기신문 본문에서 기자/제보/공유/URL복사 등 잡음 제거
    """
    s = normalize_spaces(text)

    # 이메일 제거
    s = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", " ", s)

    # 공유/제보/스크랩/URL복사/글씨키우기 등
    noise_patterns = [
        r"카카오스토리\(으\)로", r"네이버블로그\(으\)로", r"URL복사\(으\)로",
        r"페이스북\(?\)?로\s*기사보내기", r"트위터\(?\)?로\s*기사보내기",
        r"카카오톡\(?\)?으로\s*기사보내기", r"밴드\(?\)?로\s*기사보내기",
        r"기사보내기", r"기사\s*보내기", r"기사스크랩하기",
        r"본문\s*글씨\s*키우기", r"본문\s*글씨\s*줄이기",
        r"다른\s*찾기", r"닫기", r"바로가기",
        r"제보\s*제보", r"제보", r"공유", r"SNS", r"좋아요", r"구독",
        r"무단전재\s*및\s*재배포\s*금지",
    ]
    for pat in noise_patterns:
        s = re.sub(pat, " ", s, flags=re.IGNORECASE)

    # 기자명 표기 제거 (예: 홍길동 기자 / 홍길동 기자(aaa@bbb.com))
    s = re.sub(r"[가-힣]{2,4}\s*기자(\([^)]*\))?", " ", s)

    return normalize_spaces(s)

def clean_lead_prefix(text: str, source: str) -> str:
    """
    subtitle(요약)에서
    [에너지신문] / [가스신문 = 홍길동 기자] 같은 접두 표기 제거
    """
    s = normalize_spaces(text)

    if source == "에너지신문":
        s = re.sub(r"^\[\s*에너지신문\s*\]\s*", "", s)

    if source == "가스신문":
        # [가스신문 = 홍길동 기자] / [가스신문-홍길동 기자] / [가스신문] 제거
        s = re.sub(r"^\[\s*가스신문\s*(?:[-=]\s*[가-힣]{2,4}\s*기자)?\s*\]\s*", "", s)
        # 혹시 앞부분에 '홍길동 기자 =' 형태가 나오면 제거
        s = re.sub(r"^[가-힣]{2,4}\s*기자\s*=\s*", "", s)

    return normalize_spaces(s)

def clean_article_body(body: str, source: str) -> str:
    """
    본문 전체 정리(신문별)
    """
    s = normalize_spaces(body)

    if source == "전기신문":
        s = clean_electimes_noise(s)

    # 필요시 다른 신문 잡음 제거 규칙도 여기에 추가 가능
    return normalize_spaces(s)

# ==========================================
# 4. 본문 추출
# ==========================================

def extract_body(url: str, source: str) -> str:
    soup = get_soup(url)
    if not soup:
        return ""

    selectors = [
        "div#article-view-content-div",
        "div#articleBody",
        "div.article-body",
        "div.article-text",
        "article"
    ]

    body_el = None
    for sel in selectors:
        body_el = soup.select_one(sel)
        if body_el:
            break

    texts = []
    if body_el:
        for t in body_el.find_all(["p", "span", "div"]):
            txt = t.get_text(" ", strip=True)
            if txt:
                texts.append(txt)
    else:
        for p in soup.select("p"):
            txt = p.get_text(" ", strip=True)
            if txt:
                texts.append(txt)

    body = normalize_spaces(" ".join(texts))
    body = clean_article_body(body, source)

    return body if len(body) >= 40 else ""

# ==========================================
# 5. 목록 크롤러 (1~3페이지)
# ==========================================

def crawl_list(list_url, base_url, source):
    results = []

    for page in range(1, MAX_PAGES + 1):
        url_list = list_url.format(page=page)
        soup = get_soup(url_list)
        if not soup:
            continue

        items = soup.select("#section-list li")
        kept = 0
        total = 0

        for li in items:
            try:
                a = li.select_one("h2.titles a, h4.titles a, a.replace-titles, a[href*='articleView.html']")
                if not a:
                    continue

                title = a.get_text(strip=True)
                href = (a.get("href") or "").strip()
                if not href:
                    continue

                url = href if href.startswith("http") else base_url + href

                date_el = li.select_one("em.info.dated, em.replace-date")
                date = parse_date(date_el.get_text(strip=True) if date_el else "")

                total += 1

                body = extract_body(url, source)

                # 제목 or 본문에 키워드가 있어야 통과
                if not (contains_keyword(title) or contains_keyword(body)):
                    continue

                tags = make_tags(title + " " + body)

                subtitle = summarize_2lines(body)
                subtitle = clean_lead_prefix(subtitle, source)

                # subtitle이 비면 제목 기반 최소 보강
                if not subtitle:
                    subtitle = ""

                results.append({
                    "source": source,
                    "title": title,
                    "url": url,
                    "date": date,
                    "tags": tags,
                    "subtitle": subtitle,
                    "is_important": 1 if tags else 0
                })
                kept += 1
            except Exception:
                continue

        print(f"[{source}] page {page} → {kept}/{total}건 통과 ({url_list})")

    return results

# ==========================================
# 6. 저장 로직
# ==========================================

def job():
    print(f"\n[크롤링 시작] {now_str()}")

    new_items = []
    new_items += crawl_list(ENERGY_LIST, ENERGY_BASE, "에너지신문")
    new_items += crawl_list(GAS_LIST, GAS_BASE, "가스신문")
    new_items += crawl_list(ELECT_LIST, ELECT_BASE, "전기신문")

    print(f"\n[신규 수집] {len(new_items)}건\n")

    # 누적 병합(URL 기준 중복 제거)
    existing = json.loads(ALL_JSON_PATH.read_text("utf-8")) if ALL_JSON_PATH.exists() else []
    merged_map = {i["url"]: i for i in (existing + new_items) if i.get("url")}
    merged = list(merged_map.values())

    # 정렬: 최신 날짜/중요도 우선
    merged = sorted(merged, key=lambda x: (x.get("date", ""), x.get("is_important", 0)), reverse=True)

    # all.json 저장
    ALL_JSON_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    # 날짜별 저장
    by_date = {}
    for i in merged:
        by_date.setdefault(i["date"], []).append(i)

    for d, lst in by_date.items():
        (BY_DATE_DIR / f"{d}.json").write_text(
            json.dumps(lst, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # latest.json 저장
    latest_date = max(by_date.keys()) if by_date else datetime.now().strftime("%Y-%m-%d")
    latest_items = by_date.get(latest_date, [])
    LATEST_JSON_PATH.write_text(
        json.dumps(latest_items, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"[완료] all.json={len(merged)}건 | 최신날짜={latest_date} | latest.json={len(latest_items)}건")

if __name__ == "__main__":
    job()
