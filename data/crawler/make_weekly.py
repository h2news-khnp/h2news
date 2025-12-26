import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# =========================
# 설정
# =========================
KST = ZoneInfo("Asia/Seoul")

DATA_DIR = Path("data")
ALL_JSON_PATH = DATA_DIR / "all.json"
WEEKLY_JSON_PATH = DATA_DIR / "weekly.json"
WEEKLY_PROMPT_PATH = DATA_DIR / "weekly_prompt.txt"

# weekly.json에 넣을 대표 기사 개수(원하면 10으로 늘려도 됨)
TOP_ARTICLES_N = 8
TOP_KEYWORDS_N = 10

SOURCE_PRIORITY = ["에너지신문", "가스신문", "전기신문"]


# =========================
# 유틸
# =========================
def kst_now() -> datetime:
    return datetime.now(KST)

def today_str_kst() -> str:
    return kst_now().strftime("%Y-%m-%d")

def parse_date_yyyy_mm_dd(s: str) -> datetime | None:
    if not s:
        return None
    s = str(s).strip()
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return None

def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()

def safe_list(x):
    return x if isinstance(x, list) else []

def source_rank(src: str) -> int:
    if src in SOURCE_PRIORITY:
        return SOURCE_PRIORITY.index(src)
    return 999

def pick_top_articles(items: list[dict], n: int) -> list[dict]:
    """
    대표 기사 선정 로직:
    1) tags 많은 순
    2) source 우선순위(에너지,가스,전기)
    3) 제목 정렬
    """
    def key(a):
        tags_len = len(safe_list(a.get("tags")))
        return (-tags_len, source_rank(a.get("source", "")), a.get("title", ""))
    return sorted(items, key=key)[:n]

def one_liner(range_from: str, range_to: str, total: int, by_source: list[dict], top_keywords: list[dict], by_day: list[dict]) -> str:
    if total <= 0:
        return f"이번 주({range_from}~{range_to})는 수집된 기사가 없습니다."

    # 1) 최다 키워드
    top_kw = top_keywords[0]["tag"] if top_keywords else "주요 키워드"

    # 2) 최다 소스
    top_src = by_source[0] if by_source else None
    top_src_txt = f"{top_src['source']} 비중이 높았고({top_src['count']}건)" if top_src else "소스 편중이 확인되지 않았고"

    # 3) 피크데이
    peak = max(by_day, key=lambda x: x.get("count", 0)) if by_day else None
    peak_txt = f"기사량 피크는 {peak['date']}({peak['count']}건)" if peak else "기사량 피크는 확인되지 않았고"

    return f"이번 주는 ‘{top_kw}’ 이슈가 가장 두드러졌고, {top_src_txt}, {peak_txt}입니다."


# =========================
# 메인 로직
# =========================
def load_all() -> list[dict]:
    if not ALL_JSON_PATH.exists():
        return []
    try:
        return json.loads(ALL_JSON_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []

def compute_week_range(end_date: datetime) -> tuple[str, str]:
    """
    실행일(end_date) 기준 최근 7일: end_date 포함, 6일 전부터
    예) 금요일 실행 -> 토~금
    """
    end = end_date.date()
    start = (end_date - timedelta(days=6)).date()
    return (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))

def filter_items_by_range(all_items: list[dict], range_from: str, range_to: str) -> list[dict]:
    d_from = parse_date_yyyy_mm_dd(range_from)
    d_to = parse_date_yyyy_mm_dd(range_to)
    if not d_from or not d_to:
        return []

    out = []
    for a in all_items:
        d = parse_date_yyyy_mm_dd(a.get("date", ""))
        if not d:
            continue
        if d_from.date() <= d.date() <= d_to.date():
            out.append(a)
    return out

def build_by_day(items: list[dict], range_from: str, range_to: str) -> list[dict]:
    """
    기간 내 날짜를 모두 채워 0건도 표시
    """
    d_from = parse_date_yyyy_mm_dd(range_from)
    d_to = parse_date_yyyy_mm_dd(range_to)
    if not d_from or not d_to:
        return []

    counts = Counter(a.get("date") for a in items if a.get("date"))
    cur = d_from
    out = []
    while cur <= d_to:
        ds = cur.strftime("%Y-%m-%d")
        out.append({"date": ds, "count": int(counts.get(ds, 0))})
        cur += timedelta(days=1)
    return out

def build_weekly_json(all_items: list[dict]) -> dict:
    end_dt = kst_now()
    range_from, range_to = compute_week_range(end_dt)

    week_items = filter_items_by_range(all_items, range_from, range_to)

    # totals
    total = len(week_items)

    # by_source
    src_counter = Counter(a.get("source", "") for a in week_items if a.get("source"))
    by_source = [{"source": k, "count": int(v)} for k, v in src_counter.items()]
    by_source.sort(key=lambda x: (-x["count"], source_rank(x["source"]), x["source"]))

    # top_keywords
    kw_counter = Counter()
    for a in week_items:
        for t in safe_list(a.get("tags")):
            kw_counter[t] += 1
    top_keywords = [{"tag": k, "count": int(v)} for k, v in kw_counter.most_common(TOP_KEYWORDS_N)]

    # by_day
    by_day = build_by_day(week_items, range_from, range_to)

    # top_articles
    chosen = pick_top_articles(week_items, TOP_ARTICLES_N)
    top_articles = []
    for a in chosen:
        top_articles.append({
            "date": a.get("date", ""),
            "source": a.get("source", ""),
            "title": a.get("title", ""),
            "url": a.get("url", ""),
            "tags": safe_list(a.get("tags")),
            # weekly.json에도 subtitle이 있으면 분석 품질이 확 올라감
            "subtitle": normalize_spaces(a.get("subtitle", ""))[:400]
        })

    weekly = {
        "range": {"from": range_from, "to": range_to},
        "total": total,
        "by_source": by_source,
        "top_keywords": top_keywords,
        "by_day": by_day,
        "top_articles": top_articles,
        "one_liner": one_liner(range_from, range_to, total, by_source, top_keywords, by_day)
    }
    return weekly

def build_weekly_prompt_txt(weekly: dict) -> str:
    """
    ChatGPT에 붙여넣기 좋은 형태(데이터 + 기사 근거)
    """
    r = weekly.get("range", {})
    rf = r.get("from", "")
    rt = r.get("to", "")
    total = weekly.get("total", 0)

    lines = []
    lines.append("【주간 뉴스 데이터(자동 생성)】")
    lines.append(f"- 기간: {rf} ~ {rt} (최근 7일)")
    lines.append(f"- 주간 기사 수: {total}건")
    lines.append("")

    lines.append("1) 신문사별 기사 수")
    for x in weekly.get("by_source", []):
        lines.append(f"- {x.get('source','')}: {x.get('count',0)}건")
    lines.append("")

    lines.append("2) 키워드 TOP")
    for x in weekly.get("top_keywords", []):
        lines.append(f"- {x.get('tag','')}: {x.get('count',0)}")
    lines.append("")

    lines.append("3) 일자별 기사 수")
    for x in weekly.get("by_day", []):
        lines.append(f"- {x.get('date','')}: {x.get('count',0)}건")
    lines.append("")

    lines.append("4) 대표 기사(근거용)")
    arts = weekly.get("top_articles", [])
    if not arts:
        lines.append("- (없음)")
    else:
        for i, a in enumerate(arts, 1):
            title = normalize_spaces(a.get("title", ""))
            src = a.get("source", "")
            dt = a.get("date", "")
            url = a.get("url", "")
            tags = ", ".join(safe_list(a.get("tags")))
            sub = normalize_spaces(a.get("subtitle", ""))
            lines.append(f"{i}. [{dt} | {src}] {title}")
            lines.append(f"   - URL: {url}")
            if tags:
                lines.append(f"   - TAGS: {tags}")
            if sub:
                lines.append(f"   - 요약: {sub}")
            lines.append("")

    lines.append("5) 한 줄 요약(자동)")
    lines.append(f"- {weekly.get('one_liner','')}".strip())
    lines.append("")

    lines.append("【작성 요청】")
    lines.append("위 데이터를 근거로, 다음 형식의 ‘주간 트렌드 미니 리포트’를 작성해줘:")
    lines.append("1) 한 줄 결론(25~35자)")
    lines.append("2) Top 이슈 3개(핵심/근거/시사점)")
    lines.append("3) 사업기회 시그널 Top3(기회/가정/다음 액션)")
    lines.append("4) 리스크·체크포인트 Top3(리스크/영향/대응)")
    lines.append("5) 조직별 코멘트 문장 템플릿(신사업기획/개발/기술/해외/운영)")
    lines.append("6) 다음 주 ‘5분 컷’ 체크박스 질문 5개")
    lines.append("")

    return "\n".join(lines)

def main():
    DATA_DIR.mkdir(exist_ok=True)

    all_items = load_all()
    weekly = build_weekly_json(all_items)

    # weekly.json 저장
    WEEKLY_JSON_PATH.write_text(
        json.dumps(weekly, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # weekly_prompt.txt 저장
    prompt_txt = build_weekly_prompt_txt(weekly)
    WEEKLY_PROMPT_PATH.write_text(prompt_txt, encoding="utf-8")

    print("[OK] weekly.json 생성:", WEEKLY_JSON_PATH)
    print("[OK] weekly_prompt.txt 생성:", WEEKLY_PROMPT_PATH)
    print("[INFO] range:", weekly.get("range"))
    print("[INFO] total:", weekly.get("total"))

if __name__ == "__main__":
    main()
