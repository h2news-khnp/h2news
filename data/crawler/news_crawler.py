import json
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from cardnews_image import make_cardnews_image

# -------------------------------------------------------
# 1. 기본 설정
# -------------------------------------------------------

BASE_URL = "https://www.gasnews.com"

GASNEWS_LIST_URL = (
    "https://www.gasnews.com/news/articleList.html?"
    "page={page}&sc_section_code=S1N9&view_type="
)

ELECTIMES_BASE_URL = "https://www.electimes.com"
ELECTIMES_LIST_URL = (
    "https://www.electimes.com/news/articleList.html?page={page}&view_type=sm"
)

# -------------------------------------------------------
# 2. 수소 키워드 (모든 신문 공통)
# -------------------------------------------------------

HYDROGEN_KEYWORDS = [
    "수소", "연료전지", "그린수소", "청정수소", "블루수소", "원자력",
    "PAFC", "SOFC", "MCFC", "PEM", "재생", "배출권", "히트펌프", "도시가스", "구역전기", "PPA",
    "수전해", "전해조", "PEMEC", "AEM", "알카라인", "분산", "NDC", "핑크수소",
    "암모니아", "암모니아크래킹", "CCU", "CCUS", "기후부", "ESS", "배터리",
    "수소생산", "수소저장", "액화수소",
    "충전소", "수소버스", "수소차", "인프라",
    "한수원", "두산퓨얼셀", "한화임팩트", "현대차",
    "HPS", "HPC", "REC", "RPS",
]


def contains_hydrogen_keyword(text: str) -> bool:
    text = (text or "").lower()
    return any(kw.lower() in text for kw in HYDROGEN_KEYWORDS)


# -------------------------------------------------------
# 3. 날짜 변환
# -------------------------------------------------------

def normalize_gasnews_date(raw: str) -> str:
    raw = (raw or "").strip()
    year = datetime.now().year
    try:
        return datetime.strptime(f"{year}.{raw}", "%Y.%m.%d %H:%M").strftime("%Y-%m-%d")
    except Exception:
        try:
            return datetime.strptime(f"{year}.{raw}", "%Y.%m.%d").strftime("%Y-%m-%d")
        except Exception:
            return datetime.now().strftime("%Y-%m-%d")


def normalize_electimes_date(raw: str) -> str:
    raw = (raw or "").strip()
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return datetime.now().strftime("%Y-%m-%d")


# -------------------------------------------------------
# 4. 태그 자동 생성
# -------------------------------------------------------

def make_tags(title: str) -> list[str]:
    title = title or ""
    tags = [kw for kw in HYDROGEN_KEYWORDS if kw.lower() in title.lower()]
    return list(dict.fromkeys(tags))


# -------------------------------------------------------
# 5. 문장 분리 (lookbehind 오류 없는 버전)
# -------------------------------------------------------

def split_sentences(text: str) -> list[str]:
    if not text:
        return []

    cleaned = re.sub(r"\s+", " ", text).strip()

    # "다." 뒤에서 줄바꿈 처리 (아주 단순한 한국어용 heuristic)
    cleaned = cleaned.replace("다. ", "다.\n")
    cleaned = cleaned.replace("다.", "다.\n")

    # 영어식 문장부호 기준 분할 (lookbehind 고정 길이만 사용)
    parts = re.split(r"(?<=[.!?])\s+", cleaned)

    sentences = []
    for p in parts:
        for seg in p.split("\n"):
            seg = seg.strip()
            if seg:
                sentences.append(seg)

    return sentences


# -------------------------------------------------------
# 6. 본문 3줄 요약
# -------------------------------------------------------

def summarize_body(body: str, max_lines: int = 3) -> str:
    if not body:
        return ""
    sents = split_sentences(body)
    if not sents:
        return ""
    return "\n".join(sents[:max_lines])


# -------------------------------------------------------
# 7. 상세 본문 크롤링
# -------------------------------------------------------

def extract_article_body(url: str) -> str:
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"[WARN] 본문 요청 실패: {url} ({e})")
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")

    body_el = soup.select_one(
        "div#article-view-content-div, div.article-body, div#articleBody"
    )
    if not body_el:
        return ""

    texts = [
        x.get_text(" ", strip=True)
        for x in body_el.find_all(["p", "span", "div"])
    ]
    body = " ".join(texts)
    return re.sub(r"\s+", " ", body).strip()


# -------------------------------------------------------
# 8. 가스신문 크롤러
# -------------------------------------------------------

def crawl_gasnews(max_pages: int = 3) -> list[dict]:
    results: list[dict] = []

    for page in range(1, max_pages + 1):
        url = GASNEWS_LIST_URL.format(page=page)
        print(f"[가스신문] {page} 페이지 크롤링 → {url}")

        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
        except Exception as e:
            print(f"[WARN] 가스신문 목록 요청 실패(page={page}): {e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        for li in soup.select("section#section-list ul.type1 > li"):
            try:
                title_a = li.select_one("h4.titles a")
                if not title_a:
                    continue

                title = title_a.get_text(strip=True)
                href = title_a.get("href") or ""
                article_url = href if href.startswith("http") else BASE_URL + href

                date_el = li.select_one("em.info.dated")
                date_str = normalize_gasnews_date(
                    date_el.get_text(strip=True) if date_el else ""
                )

                # 제목 기반 필터
                if not contains_hydrogen_keyword(title):
                    continue

                body = extract_article_body(article_url)
                summary_3 = summarize_body(body, max_lines=3)

                results.append(
                    {
                        "date": date_str,
                        "source": "가스신문",
                        "title": title,
                        "url": article_url,
                        "body": body,
                        "summary": summary_3,
                        "tags": make_tags(title),
                    }
                )
            except Exception as e:
                print(f"[WARN] 가스신문 기사 파싱 실패: {e}")
                continue

    return results


# -------------------------------------------------------
# 9. 전기신문 크롤러
# -------------------------------------------------------

def crawl_electimes(max_pages: int = 3) -> list[dict]:
    results: list[dict] = []

    for page in range(1, max_pages + 1):
        url = ELECTIMES_LIST_URL.format(page=page)
        print(f"[전기신문] {page} 페이지 크롤링 → {url}")

        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
        except Exception as e:
            print(f"[WARN] 전기신문 목록 요청 실패(page={page}): {e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        for li in soup.select("#section-list ul.type > li.item"):
            try:
                title_a = li.select_one("div.view-cont h4.titles a.replace-titles")
                if not title_a:
                    continue

                title = title_a.get_text(strip=True)
                href = title_a.get("href") or ""
                article_url = (
                    href if href.startswith("http") else ELECTIMES_BASE_URL + href
                )

                date_el = li.select_one("div.view-cont em.replace-date")
                date_str = normalize_electimes_date(
                    date_el.get_text(strip=True) if date_el else ""
                )

                summary_el = li.select_one("div.view-cont p.lead a.replace-read")
                summary_text = (
                    summary_el.get_text(strip=True) if summary_el else ""
                )

                # 제목 + 리드문 기반 필터
                if not contains_hydrogen_keyword(f"{title} {summary_text}"):
                    continue

                body = extract_article_body(article_url)
                summary_3 = summarize_body(body, max_lines=3)

                results.append(
                    {
                        "date": date_str,
                        "source": "전기신문",
                        "title": title,
                        "url": article_url,
                        "body": body,
                        "summary": summary_3,
                        "tags": make_tags(title),
                    }
                )
            except Exception as e:
                print(f"[WARN] 전기신문 기사 파싱 실패: {e}")
                continue

    return results


# -------------------------------------------------------
# 10. 메인: 오늘 기사 + 카드뉴스 PNG + JSON 저장
# -------------------------------------------------------

def main():
    today = datetime.now().strftime("%Y-%m-%d")

    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    all_articles: list[dict] = []
    all_articles.extend(crawl_gasnews(max_pages=3))
    all_articles.extend(crawl_electimes(max_pages=3))

    # 오늘 날짜 기사만 필터
    today_articles = [a for a in all_articles if a.get("date") == today]

    # 카드뉴스 이미지 생성
    for idx, article in enumerate(today_articles, start=1):
        card_text = f"{article['title']}\n\n{article['summary']}"
        image_filename = f"{today}_{idx}.png"
        image_path = data_dir / image_filename

        make_cardnews_image(card_text, image_path)
        article["image"] = image_filename

    # JSON 저장
    out_path = data_dir / f"{today}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(today_articles, f, ensure_ascii=False, indent=2)

    print(f"\n🟢 완료: {len(today_articles)}건 → {out_path}")
    print("🟢 카드뉴스 PNG도 data/ 폴더에 생성됨")


if __name__ == "__main__":
    main()
