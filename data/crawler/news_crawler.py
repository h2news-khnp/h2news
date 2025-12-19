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
DEBUG = True

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

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


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
        if k.lower() in low and k not in seen:
            seen.add(k)
            out.append(k)
    return out

def parse_date_flexible(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None

    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d", "%Y-%m-%d", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    year = kst_now().year
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            return datetime.strptime(f"{year}.{raw}", fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None

def split_sentences_ko(text: str) -> list[str]:
    if not text:
        return []
    s = normalize_spaces(text)
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
# 3. 제목 누락 방지(목록 li에서 title robust 추출)
# ==========================================

def extract_title_from_li(li) -> str:
    a = li.select_one("h2.titles a, h4.titles a, a.replace-titles, a[href*='articleView.html']")
    if not a:
        return ""

    t = normalize_spaces(a.get_text(" ", strip=True))

    # ✅ 텍스트가 비는 케이스 방어: title/data-title 속성, 주변 노드 fallback
    if not t:
        for attr in ("title", "data-title", "aria-label"):
            v = a.get(attr)
            if v:
                t = normalize_spaces(v)
                if t:
                    break

    if not t:
        titles_node = li.select_one(".titles")
        if titles_node:
            t = normalize_spaces(titles_node.get_text(" ", strip=True))

    # 마지막 안전장치: a 전체 텍스트 재시도
    if not t:
        t = normalize_spaces("".join(a.stripped_strings))

    return t


# ==========================================
# 4. 본문 정제 (공통 + 전기신문 특화)
# ==========================================

def remove_common_blocks(root_tag):
    """모든 신문 공통: 본문 영역 안의 script/style/iframe/광고 배너 제거"""
    if not root_tag:
        return
    for t in root_tag.select("script, style, iframe, noscript"):
        t.decompose()
    for t in root_tag.select("[id^='AD'], .ad-template, .banner_box, .AD, .adsbygoogle"):
        t.decompose()

def clean_common_noise(text: str) -> str:
    s = normalize_spaces(text)
    s = re.sub(r"무단전재\s*및\s*재배포\s*금지", " ", s)
    s = EMAIL_RE.sub(" ", s)
    return normalize_spaces(s)

def remove_electimes_blocks(article_tag):
    """전기신문: 공통 제거 + 공유/유틸 블록 추가 제거"""
    remove_common_blocks(article_tag)
    for t in article_tag.select(".sns, .share, .article-share, .utility, .view-sns, .article-sns, .article-view-sns"):
        t.decompose()

def clean_electimes_noise_text(text: str) -> str:
    s = normalize_spaces(text)

    # 이메일 제거
    s = EMAIL_RE.sub(" ", s)

    # 기자명 제거
    s = re.sub(r"[가-힣]{2,4}\s*기자", " ", s)

    # 공유/기능 문구 제거
    noise_phrases = [
        "카카오스토리", "네이버블로그", "URL복사", "기사스크랩",
        "본문 글씨 키우기", "본문 글씨 줄이기",
        "닫기", "바로가기",
        "공유", "제보", "트위터", "페이스북", "카카오톡", "밴드",
    ]
    for ph in noise_phrases:
        s = s.replace(ph, " ")

    # "(으)로" 등 이상 토큰 제거
    s = re.sub(r"\(\s*\)\s*\(으\)로", " ", s)
    s = re.sub(r"\(으\)로", " ", s)

    return normalize_spaces(s)


# ==========================================
# 5. 기사 상세에서 발행일/본문 추출
# ==========================================

def extract_published_date_from_article(soup: BeautifulSoup) -> str | None:
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
            m2 = re.search(r"(\d{4}-\d{2}-\d{2})", content)
            if m2:
                return m2.group(1)

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

    # 전기신문
    if source == "전기신문":
        article_tag = soup.select_one("article#article-view-content-div") or soup.select_one("div#article-view-content-div")
        if article_tag:
            remove_electimes_blocks(article_tag)

            parts = []
            sub = article_tag.select_one("h4.subheading")
            if sub:
                parts.append(sub.get_text(" ", strip=True))

            # ✅ p 중심
            for p in article_tag.find_all("p"):
                txt = p.get_text(" ", strip=True)
                if txt:
                    parts.append(txt)

            body = normalize_spaces(" ".join(parts))
            body = clean_common_noise(body)
            body = clean_electimes_noise_text(body)
            return (body if len(body) >= 60 else ""), published

    # 에너지/가스 포함 공통
    selectors = [
        "div#article-view-content-div",
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
        remove_common_blocks(body_el)

        # ✅ 공통도 p 위주
        for p in body_el.find_all("p"):
            t = p.get_text(" ", strip=True)
            if t:
                texts.append(t)

        # p가 너무 없으면 안전 fallback
        if len(" ".join(texts)) < 80:
            fallback = body_el.get_text(" ", strip=True)
            if fallback:
                texts = [fallback]
    else:
        for p in soup.select("p"):
            t = p.get_text(" ", strip=True)
            if t:
                texts.append(t)

    body = normalize_spaces(" ".join(texts))
    body = clean_common_noise(body)
    return (body if len(body) >= 60 else ""), published


# ==========================================
# 6. 목록 크롤러 (1~3페이지)
# ==========================================

def crawl_list(list_url: str, base_url: str, source: str) -> list[dict]:
    results = []

    for page in range(1, MAX_PAGES + 1):
        page_url = list_url.format(page=page)
        soup = get_soup(page_url)
        if not soup:
            continue

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

                href = (a.get("href", "") or "").strip()
                if not href:
                    continue
                url = href if href.startswith("http") else base_url + href

                title = extract_title_from_li(li)
                total += 1

                # ✅ 타이틀이 비면 스킵(카드에서 제목 공백 방지)
                if not title:
                    if DEBUG:
                        print(f"[WARN] {source} 제목 비어 스킵: {url}")
                    continue

                body, pub_date = extract_body_from_article(url, source)

                if not (contains_keyword(title) or contains_keyword(body)):
                    continue

                tags = make_tags(title + " " + body)
                subtitle = summarize_2lines(body)

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
                    "is_important": 1 if tags else 0
                })
                kept += 1

            except Exception as e:
                if DEBUG:
                    print(f"[WARN] {source} 항목 스킵: {e}")
                continue

        print(f"[{source}] page {page} → {kept}건 / 목록 {total}개 | {page_url}")

    return results


# ==========================================
# 7. 저장 로직 (all / by_date / latest(today))
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

    existing = load_all_existing()
    merged = dedup_by_url(existing + new_items)
    merged = sort_articles(merged)

    ALL_JSON_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    by_date = write_by_date(merged)

    today = today_kst_str()
    latest_items = sort_articles(by_date.get(today, []))
    LATEST_JSON_PATH.write_text(json.dumps(latest_items, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[저장 완료] all.json={len(merged)}건 | by_date={len(by_date)}일 | latest(today)={len(latest_items)}건")

if __name__ == "__main__":
    job()
