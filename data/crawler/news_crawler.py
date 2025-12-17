import json
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:
    ZoneInfo = None

# ==========================================
# 0. 시간대(한국) 고정
# ==========================================
KST = ZoneInfo("Asia/Seoul") if ZoneInfo else None

def now_kst():
    return datetime.now(KST) if KST else datetime.now()

def today_kst_str():
    return now_kst().strftime("%Y-%m-%d")

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
DAILY_DIR = DATA_DIR / "daily"
DATA_DIR.mkdir(exist_ok=True)
DAILY_DIR.mkdir(parents=True, exist_ok=True)

LATEST_JSON_PATH = DATA_DIR / "latest.json"
DAILY_INDEX_PATH = DAILY_DIR / "index.json"

# 페이지 1~3 자동 크롤링
MAX_PAGES = 3

# ==========================================
# 2. 공통 유틸
# ==========================================
def get_soup(url: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        return BeautifulSoup(res.text, "html.parser")
    except Exception as e:
        print(f"[ERROR] GET 실패: {url} → {e}")
        return None

def has_any_keyword(text: str) -> bool:
    if not text:
        return False
    low = text.lower()
    return any(kw.lower() in low for kw in KEYWORDS)

def extract_tags(text: str):
    if not text:
        return []
    low = text.lower()
    tags = [kw for kw in KEYWORDS if kw.lower() in low]
    # 중복 제거(순서 유지)
    return list(dict.fromkeys(tags))

def normalize_date_common(raw: str) -> str:
    """
    '2025.12.10', '2025.12.10 09:30', '2025-12-10', '12.10 09:30' 등 대응
    """
    if not raw:
        return today_kst_str()

    raw = raw.strip()

    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 연도 없는 경우는 KST 기준 연도 사용
    year = now_kst().year
    try:
        return datetime.strptime(f"{year}.{raw}", "%Y.%m.%d %H:%M").strftime("%Y-%m-%d")
    except Exception:
        try:
            return datetime.strptime(f"{year}.{raw}", "%Y.%m.%d").strftime("%Y-%m-%d")
        except Exception:
            return today_kst_str()

# ==========================================
# 3. 본문 추출 + 2문장 요약
# ==========================================
def extract_article_body(url: str) -> str:
    soup = get_soup(url)
    if not soup:
        return ""

    body_el = soup.select_one(
        "div#article-view-content-div, "
        "div.article-body, "
        "div#articleBody, "
        "div.article-text"
    )

    if body_el:
        texts = [x.get_text(" ", strip=True) for x in body_el.find_all(["p", "span", "div"])]
    else:
        texts = [p.get_text(" ", strip=True) for p in soup.select("p")]

    body = " ".join(texts)
    body = re.sub(r"\s+", " ", body).strip()
    return body

def split_sentences(text: str):
    if not text:
        return []
    cleaned = re.sub(r"\s+", " ", text).strip()

    # 한국어 종결 "다." 기준 줄바꿈
    cleaned = cleaned.replace("다. ", "다.\n").replace("다.", "다.\n")

    # 고정 길이 lookbehind만 사용
    parts = re.split(r"(?<=[.!?])\s+", cleaned)

    sents = []
    for p in parts:
        for seg in p.split("\n"):
            seg = seg.strip()
            if seg:
                sents.append(seg)
    return sents

def summarize_body_2sent(body: str) -> str:
    sents = split_sentences(body)
    if not sents:
        return ""
    # index.html에서 2줄 clamp라서, \n 대신 공백으로 합쳐도 됨
    return " ".join(sents[:2]).strip()

# ==========================================
# 4. 신문별 크롤러 (1~3페이지)
#    - 제목+본문 모두에서 키워드 판단
# ==========================================
def crawl_energy_news(max_pages: int = 3):
    print("[에너지신문] 크롤링 시작")
    results = []
    base = "https://www.energy-news.co.kr"

    for page in range(1, max_pages + 1):
        url = f"{base}/news/articleList.html?page={page}&view_type=sm"
        soup = get_soup(url)
        if not soup:
            continue

        # 에너지신문은 type1/section-list 구조가 자주 바뀌어서 후보를 넓게 잡음
        items = soup.select("#section-list .type1 li, #section-list ul.type1 > li, #section-list li")
        for it in items:
            a = it.select_one("h2.titles a, h4.titles a")
            if not a:
                continue

            title = a.get_text(strip=True)
            link = a.get("href", "")
            if not link:
                continue
            if not link.startswith("http"):
                link = base + link

            date_el = it.select_one("em.info.dated")
            raw_date = date_el.get_text(strip=True) if date_el else ""
            date = normalize_date_common(raw_date)

            body = extract_article_body(link)
            judge_text = f"{title} {body}"

            # 제목+본문에서 키워드 판단
            if not has_any_keyword(judge_text):
                continue

            tags = extract_tags(judge_text)
            subtitle = summarize_body_2sent(body)

            results.append({
                "source": "에너지신문",
                "title": title,
                "url": link,
                "date": date,
                "tags": tags,
                "subtitle": subtitle
            })

    print(f"[에너지신문] 수집 {len(results)}건")
    return results

def crawl_gas_news(max_pages: int = 3):
    print("[가스신문] 크롤링 시작")
    results = []
    base = "https://www.gasnews.com"

    for page in range(1, max_pages + 1):
        url = f"{base}/news/articleList.html?page={page}&view_type=sm"
        soup = get_soup(url)
        if not soup:
            continue

        items = soup.select("#section-list .type1 li, #section-list ul.type1 > li, #section-list li")
        for it in items:
            a = it.select_one("h2.titles a, h4.titles a")
            if not a:
                continue

            title = a.get_text(strip=True)
            link = a.get("href", "")
            if not link:
                continue
            if not link.startswith("http"):
                link = base + link

            date_el = it.select_one("em.info.dated")
            raw_date = date_el.get_text(strip=True) if date_el else ""
            date = normalize_date_common(raw_date)

            body = extract_article_body(link)
            judge_text = f"{title} {body}"
            if not has_any_keyword(judge_text):
                continue

            tags = extract_tags(judge_text)
            subtitle = summarize_body_2sent(body)

            results.append({
                "source": "가스신문",
                "title": title,
                "url": link,
                "date": date,
                "tags": tags,
                "subtitle": subtitle
            })

    print(f"[가스신문] 수집 {len(results)}건")
    return results

def crawl_electric_news(max_pages: int = 3):
    print("[전기신문] 크롤링 시작")
    results = []
    base = "https://www.electimes.com"

    for page in range(1, max_pages + 1):
        url = f"{base}/news/articleList.html?page={page}&view_type=sm"
        soup = get_soup(url)
        if not soup:
            continue

        items = soup.select("#section-list .type1 li, #section-list ul.type1 > li, #section-list li")
        for it in items:
            a = it.select_one("h2.titles a, h4.titles a")
            if not a:
                continue

            title = a.get_text(strip=True)
            link = a.get("href", "")
            if not link:
                continue
            if not link.startswith("http"):
                link = base + link

            date_el = it.select_one("em.info.dated")
            raw_date = date_el.get_text(strip=True) if date_el else ""
            date = normalize_date_common(raw_date)

            body = extract_article_body(link)
            judge_text = f"{title} {body}"
            if not has_any_keyword(judge_text):
                continue

            tags = extract_tags(judge_text)
            subtitle = summarize_body_2sent(body)

            results.append({
                "source": "전기신문",
                "title": title,
                "url": link,
                "date": date,
                "tags": tags,
                "subtitle": subtitle
            })

    print(f"[전기신문] 수집 {len(results)}건")
    return results

# ==========================================
# 5. 저장 로직 (latest + daily + index)
# ==========================================
def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def update_daily_index():
    # daily 폴더 내 YYYY-MM-DD.json 목록을 최신순으로 저장
    dates = []
    for p in DAILY_DIR.glob("*.json"):
        if p.name == "index.json":
            continue
        name = p.stem  # "2025-12-17"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", name):
            dates.append(name)
    dates = sorted(set(dates))
    write_json(DAILY_INDEX_PATH, dates)

def job():
    run_date = today_kst_str()
    print(f"\n[START] KST 기준 실행일: {run_date}")

    all_data = []
    all_data.extend(crawl_energy_news(MAX_PAGES))
    all_data.extend(crawl_gas_news(MAX_PAGES))
    all_data.extend(crawl_electric_news(MAX_PAGES))

    # URL 기준 중복 제거
    dedup = {}
    for a in all_data:
        dedup[a["url"]] = a
    unique = list(dedup.values())

    # (선택) 날짜 내림차순, 그 다음 중요도 느낌으로 tags 많은 순
    unique.sort(key=lambda x: (x.get("date",""), len(x.get("tags",[]))), reverse=True)

    # 1) daily: 실행일(KST) 파일에는 "그 날짜 기사만" 저장
    daily = [a for a in unique if a.get("date") == run_date]
    daily_path = DAILY_DIR / f"{run_date}.json"
    write_json(daily_path, daily)
    print(f"[WRITE] {daily_path} ({len(daily)}건)")

    # 2) latest.json: index.html 기본 로드용 = daily와 동일(오늘자)
    write_json(LATEST_JSON_PATH, daily)
    print(f"[WRITE] {LATEST_JSON_PATH} ({len(daily)}건)")

    # 3) daily/index.json 갱신
    update_daily_index()
    print(f"[WRITE] {DAILY_INDEX_PATH}")

    # 디버그: 수집은 했는데 daily가 0인 경우 원인 확인용
    if len(unique) > 0 and len(daily) == 0:
        sample_dates = sorted({x.get("date","") for x in unique})[-10:]
        print(f"[WARN] 수집은 {len(unique)}건인데 '{run_date}'로 매칭된 기사가 0건")
        print(f"       수집된 날짜 샘플: {sample_dates}")

if __name__ == "__main__":
    job()
