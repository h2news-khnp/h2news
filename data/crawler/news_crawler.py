import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
from pathlib import Path
import os
import re
import time

# schedule 은 선택적 임포트 (없어도 동작)
try:
    import schedule  # type: ignore
except ImportError:
    schedule = None

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
DATA_DIR.mkdir(exist_ok=True)
LATEST_JSON_PATH = DATA_DIR / "latest.json"


# ==========================================
# 2. 유틸 함수
# ==========================================

def get_soup(url: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        return BeautifulSoup(res.text, "html.parser")
    except Exception as e:
        print(f"[ERROR] {url} → {e}")
        return None


def check_keywords(title: str):
    lower = title.lower()
    return [kw for kw in KEYWORDS if kw.lower() in lower]


def normalize_date_common(raw: str):
    if not raw:
        return datetime.now().strftime("%Y-%m-%d")

    raw = raw.strip()

    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    year = datetime.now().year
    try:
        return datetime.strptime(f"{year}.{raw}", "%Y.%m.%d %H:%M").strftime("%Y-%m-%d")
    except Exception:
        try:
            return datetime.strptime(f"{year}.{raw}", "%Y.%m.%d").strftime("%Y-%m-%d")
        except Exception:
            return datetime.now().strftime("%Y-%m-%d")


# ==========================================
# 3. 본문 추출 & 요약 (subtitle 용 2줄)
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

    if not body_el:
        texts = [p.get_text(" ", strip=True) for p in soup.select("p")]
    else:
        texts = [x.get_text(" ", strip=True) for x in body_el.find_all(["p", "span", "div"])]

    body = " ".join(texts)
    return re.sub(r"\s+", " ", body).strip()


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


def summarize_body(body: str, max_lines: int = 2) -> str:
    sents = split_sentences(body)
    if not sents:
        return ""
    return "\n".join(sents[:max_lines])


# ==========================================
# 4. 개별 신문 크롤러
# ==========================================

def crawl_energy_news():
    print("[에너지신문] 시작")
    results = []
    base = "https://www.energy-news.co.kr"
    url = f"{base}/news/articleList.html?view_type=sm"

    soup = get_soup(url)
    if not soup:
        return results

    for art in soup.select("#section-list .type1 li"):
        try:
            t = art.select_one("h2.titles a")
            if not t:
                continue

            title = t.get_text(strip=True)
            link = t["href"]
            if not link.startswith("http"):
                link = base + link

            date_raw = art.select_one("em.info.dated").get_text(strip=True) if art.select_one("em.info.dated") else ""
            date = normalize_date_common(date_raw)

            tags = check_keywords(title)
            body = extract_article_body(link)
            summary = summarize_body(body, 2).replace("\n", " ")

            results.append({
                "source": "에너지신문",
                "title": title,
                "url": link,
                "date": date,
                "tags": tags,
                "subtitle": summary,
                "is_important": len(tags) > 0
            })
        except Exception:
            continue

    return results


def crawl_gas_news():
    print("[가스신문] 시작")
    results = []
    base = "https://www.gasnews.com"
    url = f"{base}/news/articleList.html?view_type=sm"

    soup = get_soup(url)
    if not soup:
        return results

    articles = soup.select("#section-list .type1 li")
    if not articles:
        articles = soup.select(".article-list .list-block")

    for art in articles:
        try:
            t = art.select_one("h2.titles a") or art.select_one("h4.titles a")
            if not t:
                continue

            title = t.get_text(strip=True)
            link = t["href"]
            if not link.startswith("http"):
                link = base + link

            date_raw = art.select_one("em.info.dated").get_text(strip=True) if art.select_one("em.info.dated") else ""
            date = normalize_date_common(date_raw)

            tags = check_keywords(title)
            body = extract_article_body(link)
            summary = summarize_body(body, 2).replace("\n", " ")

            results.append({
                "source": "가스신문",
                "title": title,
                "url": link,
                "date": date,
                "tags": tags,
                "subtitle": summary,
                "is_important": len(tags) > 0
            })
        except Exception:
            continue

    return results


def crawl_electric_news():
    print("[전기신문] 시작")
    results = []
    base = "https://www.electimes.com"
    url = f"{base}/news/articleList.html?view_type=sm"

    soup = get_soup(url)
    if not soup:
        return results

    for art in soup.select("#section-list .type1 li"):
        try:
            t = art.select_one("h2.titles a") or art.select_one("h4.titles a")
            if not t:
                continue

            title = t.get_text(strip=True)
            link = t["href"]
            if not link.startswith("http"):
                link = base + link

            date_raw = art.select_one("em.info.dated").get_text(strip=True) if art.select_one("em.info.dated") else ""
            date = normalize_date_common(date_raw)

            tags = check_keywords(title)
            body = extract_article_body(link)
            summary = summarize_body(body, 2).replace("\n", " ")

            results.append({
                "source": "전기신문",
                "title": title,
                "url": link,
                "date": date,
                "tags": tags,
                "subtitle": summary,
                "is_important": len(tags) > 0
            })
        except Exception:
            continue

    return results


# ==========================================
# 5. JSON 저장 (index.html 호환 latest.json)
# ==========================================

def job():
    print("\n=== 크롤링 시작 ===")

    data = []
    data.extend(crawl_energy_news())
    data.extend(crawl_gas_news())
    data.extend(crawl_electric_news())

    # URL 기준 중복 제거
    dedup = {}
    for a in data:
        dedup[a["url"]] = a
    articles = list(dedup.values())

    # 중요 기사 우선 정렬
    articles.sort(key=lambda x: x["is_important"], reverse=True)

    # index.html 이 바로 사용하는 latest.json
    with LATEST_JSON_PATH.open("w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"[완료] {len(articles)}건 저장 → {LATEST_JSON_PATH}")


# ==========================================
# 6. 실행 엔트리
# ==========================================

if __name__ == "__main__":
    # GitHub Actions에서는 한 번만 실행
    if os.getenv("GITHUB_ACTIONS") == "true":
        job()
    else:
        # 로컬 실행: 스케줄 모듈이 있으면 08:00 / 15:00 자동 실행
        job()
        if schedule is not None:
            print("로컬에서 08:00 / 15:00 자동 실행 모드입니다.")
            schedule.every().day.at("08:00").do(job)
            schedule.every().day.at("15:00").do(job)
            while True:
                schedule.run_pending()
                time.sleep(60)
        else:
            print("스케줄 모듈이 없어 한 번만 실행했습니다. "
                  "로컬 자동 실행을 원하면 `pip install schedule` 후 다시 실행해줘.")
