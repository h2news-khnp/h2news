import json
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ============================================
# 1. 기본 설정
# ============================================

# 가스신문
GAS_BASE_URL = "https://www.gasnews.com"
GAS_LIST_URL = (
    "https://www.gasnews.com/news/articleList.html?"
    "page={page}&sc_section_code=S1N9&view_type="
)

# 전기신문
ELECT_BASE_URL = "https://www.electimes.com"
ELECT_LIST_URL = (
    "https://www.electimes.com/news/articleList.html?page={page}&view_type=sm"
)

# 저장 경로 (이 파일: data/crawler/news_crawler.py 기준)
SCRIPT_DIR = Path(__file__).resolve().parent          # .../data/crawler
DATA_DIR = SCRIPT_DIR.parent                          # .../data
CARDS_ROOT = DATA_DIR / "cards"                       # 카드뉴스 이미지 루트


# ============================================
# 2. 공통: 수소 관련 키워드
# ============================================

HYDROGEN_KEYWORDS = [
    # 기본
    "수소", "연료전지", "그린수소", "청정수소", "블루수소",
    "PAFC", "SOFC", "MCFC",

    # 수전해/전해조
    "수전해", "전해조", "PEMEC", "AEM", "알카라인",

    # 암모니아 기반
    "암모니아", "암모니아크래킹",

    # 인프라 & 정책
    "수소생산", "수소저장", "액화수소",
    "충전소", "수소버스", "수소차", "인프라",

    # 기관/기업 키워드
    "한수원", "두산퓨얼셀", "한화임팩트", "현대차",

    # 기타
    "HPS", "HPC", "REC", "RPS",
]


def contains_hydrogen_keyword(text: str) -> bool:
    """수소 관련 키워드 포함 여부."""
    if not text:
        return False
    lower = text.lower()
    return any(k.lower() in lower for k in HYDROGEN_KEYWORDS)


def make_tags(title: str, body: str = "") -> list[str]:
    """제목/본문에서 태그 추출."""
    base = (title or "") + " " + (body or "")
    tags = [kw for kw in HYDROGEN_KEYWORDS if kw.lower() in base.lower()]
    # 중복 제거
    return list(dict.fromkeys(tags))


# ============================================
# 3. 날짜 변환 함수
# ============================================

def normalize_gas_date(raw: str) -> str:
    """
    가스신문: '12.09 09:50'  -> 'YYYY-12-09'
    """
    raw = (raw or "").strip()
    year = datetime.now().year

    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(f"{year}.{raw}", fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return datetime.now().strftime("%Y-%m-%d")


def normalize_elect_date(raw: str) -> str:
    raw = (raw or "").strip()
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return datetime.now().strftime("%Y-%m-%d")


# ============================================
# 4. 상세 본문 추출 & 요약
# ============================================

def extract_article_body(url: str) -> str:
    """
    상세 기사 페이지에서 본문 텍스트만 추출.
    (가스신문/전기신문 모두 공통 패턴 우선 시도)
    """
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"[WARN] 본문 요청 실패: {url} ({e})")
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")

    # 1) 가장 흔한 패턴 시도
    candidates = [
        "#article-view-content-div",
        "section#article-view-content-div",
        "div#article-view-content-div",
        "div.article-body",
        "div#article-view-content-attach",
    ]

    for sel in candidates:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(" ", strip=True)
            if len(text) > 30:
                return text

    # 2) fallback: article 태그 전체 사용
    article_el = soup.find("article")
    if article_el:
        text = article_el.get_text(" ", strip=True)
        if len(text) > 30:
            return text

    # 3) 최종 fallback: 페이지 전체에서 p 태그 모음
    ps = soup.find_all("p")
    joined = " ".join(p.get_text(" ", strip=True) for p in ps)
    return joined.strip()


def split_sentences(text: str) -> list[str]:
    """
    아주 단순한 한국어/영어 문장 분리.
    정교하진 않지만 카드뉴스 3줄 요약용으로는 충분.
    """
    if not text:
        return []

    # 줄바꿈 → 공백
    cleaned = re.sub(r"\s+", " ", text)

    # 마침표/물음표/느낌표/‘다.’ 뒤에서 분리
    parts = re.split(r"(?<=[\.!?]|다\.)\s+", cleaned)
    sentences = [p.strip() for p in parts if p.strip()]
    return sentences


def summarize_body(body: str, max_lines: int = 3) -> str:
    """
    본문에서 앞쪽 문장 위주로 3줄 요약.
    (줄 사이에 '\n' 삽입)
    """
    sents = split_sentences(body)
    if not sents:
        return ""

    picked = sents[:max_lines]

    # 문장 개수가 모자라면, 마지막 문장을 잘라서 길이 조정
    if len(picked) < max_lines and len(sents) > max_lines:
        extra = " ".join(sents[max_lines:])
        if extra:
            picked.append(extra[:80] + "...")
    return "\n".join(picked)


# ============================================
# 5. 크롤러: 가스신문
# ============================================

def crawl_gasnews(max_pages: int = 2) -> list[dict]:
    results: list[dict] = []

    for page in range(1, max_pages + 1):
        url = GAS_LIST_URL.format(page=page)
        print(f"[가스신문] {page} 페이지 크롤링 → {url}")

        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for li in soup.select("section#section-list ul.type1 > li"):
            title_a = li.select_one("h4.titles a")
            if not title_a:
                continue

            title = title_a.get_text(strip=True)
            href = title_a.get("href") or ""
            article_url = GAS_BASE_URL + href

            date_el = li.select_one("em.info.dated")
            date_str = normalize_gas_date(date_el.get_text(strip=True) if date_el else "")

            # 필터: 제목 기준
            if not contains_hydrogen_keyword(title):
                continue

            body = extract_article_body(article_url)
            summary_3 = summarize_body(body, max_lines=3)
            tags = make_tags(title, body)

            results.append(
                {
                    "date": date_str,
                    "source": "가스신문",
                    "title": title,
                    "url": article_url,
                    "summary_3lines": summary_3,
                    "body": body,
                    "tags": tags,
                }
            )

    return results


# ============================================
# 6. 크롤러: 전기신문
# ============================================

def crawl_electimes(max_pages: int = 2) -> list[dict]:
    results: list[dict] = []

    for page in range(1, max_pages + 1):
        url = ELECT_LIST_URL.format(page=page)
        print(f"[전기신문] {page} 페이지 크롤링 → {url}")

        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for li in soup.select("#section-list ul.type > li.item"):
            title_a = li.select_one("div.view-cont h4.titles a.linked.replace-titles")
            if not title_a:
                continue

            title = title_a.get_text(strip=True)
            href = title_a.get("href") or ""
            if href.startswith("/"):
                article_url = ELECT_BASE_URL + href
            else:
                article_url = href

            date_el = li.select_one("div.view-cont em.replace-date")
            date_str = normalize_elect_date(
                date_el.get_text(strip=True) if date_el else ""
            )

            summary_el = li.select_one("div.view-cont p.lead a.replace-read")
            list_summary = summary_el.get_text(strip=True) if summary_el else ""

            # 제목 + 리스트 요약 기준 필터
            filter_text = f"{title} {list_summary}"
            if not contains_hydrogen_keyword(filter_text):
                continue

            body = extract_article_body(article_url)
            summary_3 = summarize_body(body or list_summary, max_lines=3)
            tags = make_tags(title, body)

            results.append(
                {
                    "date": date_str,
                    "source": "전기신문",
                    "title": title,
                    "url": article_url,
                    "list_summary": list_summary,
                    "summary_3lines": summary_3,
                    "body": body,
                    "tags": tags,
                }
            )

    return results


# ============================================
# 7. GPT-style '연결 기사' 간단 알고리즘
# ============================================

def build_related_map(articles: list[dict], top_k: int = 3) -> None:
    """
    아주 단순한 유사도 계산:
      - 태그 겹치는 개수
      - 제목에 공통으로 포함된 수소 키워드 개수
    상위 top_k 개를 related 리스트에 URL 기준으로 저장.
    """
    n = len(articles)
    for i in range(n):
        scores: list[tuple[float, int]] = []
        tags_i = set(articles[i].get("tags") or [])
        title_i = articles[i]["title"]

        for j in range(n):
            if i == j:
                continue

            tags_j = set(articles[j].get("tags") or [])
            title_j = articles[j]["title"]

            tag_score = len(tags_i & tags_j)
            kw_score = 0
            for kw in HYDROGEN_KEYWORDS:
                if kw in title_i and kw in title_j:
                    kw_score += 1

            score = tag_score * 2 + kw_score
            if score > 0:
                scores.append((score, j))

        scores.sort(reverse=True, key=lambda x: x[0])
        related_urls = [articles[j]["url"] for (_, j) in scores[:top_k]]
        articles[i]["related"] = related_urls


# ============================================
# 8. 카드뉴스 이미지 생성
# ============================================

from cardnews_image import make_cardnews_image


def generate_card_images(articles: list[dict], today: str) -> None:
    """
    각 기사마다 3줄 요약으로 카드뉴스 PNG 생성.
    생성된 파일 경로를 article["card_image"]에 저장.
    """
    today_dir = CARDS_ROOT / today
    today_dir.mkdir(parents=True, exist_ok=True)

    for idx, art in enumerate(articles, start=1):
        summary = art.get("summary_3lines") or art["title"]
        lines = summary.split("\n")
        # 3줄 맞추기 (모자라면 제목/날짜 추가)
        while len(lines) < 3:
            if len(lines) == 0:
                lines.append(art["title"])
            elif len(lines) == 1:
                lines.append(art["source"])
            else:
                lines.append(art["date"])

        filename = f"card_{idx:02d}.png"
        out_path = today_dir / filename

        make_cardnews_image(lines[:3], str(out_path))

        # JSON/HTML에서 사용할 상대 경로 (GitHub Pages 기준)
        art["card_image"] = f"cards/{today}/{filename}"


# ============================================
# 9. 오늘자 JSON 저장
# ============================================

def save_json(articles: list[dict], today: str) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    out_path = DATA_DIR / f"{today}.json"

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"\n🟢 JSON 저장 완료: {len(articles)}건 → {out_path}")
    return out_path


# ============================================
# 10. 메인 실행
# ============================================

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print("=== 현재 디렉토리 구조 ===")
    for p in Path(".").iterdir():
        print(p)
    print("=== 크롤러 실행 ===")

    all_articles: list[dict] = []
    all_articles.extend(crawl_gasnews(max_pages=3))
    all_articles.extend(crawl_electimes(max_pages=3))

    # 오늘 날짜 기사만 필터링
    today_articles = [a for a in all_articles if a.get("date") == today]

    # GPT-style 관련 기사 링크 계산
    build_related_map(today_articles, top_k=3)

    # 카드뉴스 이미지 생성
    generate_card_images(today_articles, today)

    # JSON 저장
    save_json(today_articles, today)


if __name__ == "__main__":
    main()
