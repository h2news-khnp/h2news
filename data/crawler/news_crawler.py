import json
import re
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

# =====================================================
# 1. 기본 설정
# =====================================================

BASE_URL = "https://www.gasnews.com"
GASNEWS_LIST_URL = (
    "https://www.gasnews.com/news/articleList.html?"
    "page={page}&sc_section_code=S1N9&view_type="
)

ELECTIMES_BASE_URL = "https://www.electimes.com"
ELECTIMES_LIST_URL = "https://www.electimes.com/news/articleList.html?page={page}&view_type=sm"

# =====================================================
# 2. 수소 관련 키워드
# =====================================================

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

def contains_hydrogen_keyword(text: str) -> bool:
    text = text.lower()
    return any(kw.lower() in text for kw in HYDROGEN_KEYWORDS)

def make_tags(text: str) -> list[str]:
    tags = [kw for kw in HYDROGEN_KEYWORDS if kw.lower() in text.lower()]
    return list(dict.fromkeys(tags))


# =====================================================
# 3. 날짜 처리
# =====================================================

def normalize_gasnews_date(raw: str) -> str:
    raw = raw.strip()
    year = datetime.now().year
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            return datetime.strptime(f"{year}.{raw}", fmt).strftime("%Y-%m-%d")
        except:
            continue
    return datetime.now().strftime("%Y-%m-%d")

def normalize_electimes_date(raw: str) -> str:
    raw = raw.strip()
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except:
            continue
    return datetime.now().strftime("%Y-%m-%d")


# =====================================================
# 4. 본문 크롤링
# =====================================================

def extract_article_body(url: str) -> str:
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except:
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")

    # 여러 신문사에 대응하는 본문 선택자
    body_el = soup.select_one(
        "div#article-view-content-div, div#articleBody, div.article-body, div#CmAdContent"
    )
    if not body_el:
        return ""

    text = " ".join(x.get_text(" ", strip=True) for x in body_el.find_all(["p", "div", "span"]))
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"기자$", "", text)

    # 불필요한 홍보 문구 제거
    text = re.sub(r"ⓒ.*?무단전재.*?$", "", text)

    return text.strip()


# =====================================================
# 5. 한국어 문장 분리 (업그레이드)
# =====================================================

# 한국어 문장 종결 패턴 → "다.", "했다.", "됐다.", "한다.", "하였다."
KOREAN_END = r"(다\.|했다\.|하였다\.|한다\.|됐다\.|되었다\.)"

def split_sentences(text: str):
    if not text:
        return []

    # KOREAN_END 뒤에서 줄바꿈 삽입
    modified = re.sub(KOREAN_END, r"\1\n", text)

    # 영어 및 기타 문장부호 단위 분리
    parts = re.split(r"(?<=[.!?])\s+", modified)

    result = []
    for part in parts:
        for line in part.split("\n"):
            cleaned = line.strip()
            if len(cleaned) > 10:    # 너무 짧은 문장은 제거
                result.append(cleaned)

    return result


# =====================================================
# 6. 요약: 앞의 3문장만 추출
# =====================================================

def summarize_body(text: str, max_lines: int = 3) -> str:
    sents = split_sentences(text)
    if not sents:
        return ""

    return "\n".join(sents[:max_lines])


# =====================================================
# 7. 가스신문
# =====================================================

def crawl_gasnews(max_pages: int = 3):
    results = []

    for page in range(1, max_pages + 1):
        url = GASNEWS_LIST_URL.format(page=page)
        print(f"[가스신문] {page} → {url}")

        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for li in soup.select("section#section-list ul.type1 > li"):
            title_el = li.select_one("h4.titles a")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            if not contains_hydrogen_keyword(title):
                continue

            link = BASE_URL + title_el.get("href")

            date = normalize_gasnews_date(li.select_one("em.info.dated").text)

            body = extract_article_body(link)
            summary = summarize_body(body)

            results.append({
                "date": date,
                "source": "가스신문",
                "title": title,
                "url": link,
                "summary": summary,
                "tags": make_tags(title + " " + body)
            })

    return results


# =====================================================
# 8. 전기신문
# =====================================================

def crawl_electimes(max_pages: int = 3):
    results = []

    for page in range(1, max_pages + 1):
        url = ELECTIMES_LIST_URL.format(page=page)
        print(f"[전기신문] {page} → {url}")

        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for li in soup.select("#section-list ul.type > li.item"):
            title_el = li.select_one("h4.titles a.replace-titles")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)

            summary_el = li.select_one("p.lead a.replace-read")
            preview = summary_el.get_text(strip=True) if summary_el else ""

            if not contains_hydrogen_keyword(title + " " + preview):
                continue

            link = ELECTIMES_BASE_URL + title_el.get("href")
            date = normalize_electimes_date(li.select_one("em.replace-date").text)

            body = extract_article_body(link)
            summary = summarize_body(body)

            results.append({
                "date": date,
                "source": "전기신문",
                "title": title,
                "url": link,
                "summary": summary,
                "tags": make_tags(title + " " + body)
            })

    return results


# =====================================================
# 9. 메인 실행
# =====================================================

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    print("=== H2 뉴스 자동 크롤링 시작 ===")

    # 1) 원시 기사 수집
    raw_articles = []
    raw_articles.extend(crawl_gasnews(max_pages=3))
    raw_articles.extend(crawl_electimes(max_pages=3))

    # 2) URL 기준으로 중복 제거
    unique_by_url = {}
    for a in raw_articles:
        key = a.get("url")
        if not key:
            continue
        if key in unique_by_url:
            # 이미 있으면, 더 긴 summary 쪽으로 갱신 정도는 선택사항
            old = unique_by_url[key]
            if len(a.get("summary", "")) > len(old.get("summary", "")):
                unique_by_url[key] = a
        else:
            unique_by_url[key] = a

    deduped_articles = list(unique_by_url.values())

    # 3) 오늘 날짜만 필터
    today_articles = [a for a in deduped_articles if a.get("date") == today]

    # 4) 오늘 날짜 파일 (아카이브 용)
    dated_json = data_dir / f"{today}.json"
    with dated_json.open("w", encoding="utf-8") as f:
        json.dump(today_articles, f, ensure_ascii=False, indent=2)

    # 5) latest.json (프론트에서 이 파일만 사용)
    latest_json = data_dir / "latest.json"
    with latest_json.open("w", encoding="utf-8") as f:
        json.dump(today_articles, f, ensure_ascii=False, indent=2)

    print(f"[정리] 원시 {len(raw_articles)}건 → 중복 제거 {len(deduped_articles)}건")
    print(f"[완료] 오늘 기사 {len(today_articles)}건 → {dated_json.name}, latest.json 저장")


if __name__ == "__main__":
    main()
