import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path("data")
ALL_JSON_PATH = DATA_DIR / "all.json"
WEEKLY_JSON_PATH = DATA_DIR / "weekly.json"

# ===== 설정 =====
DAYS = 7          # 최근 7일
TOP_TAGS = 5      # 주간 TOP 키워드
TOP_ARTICLES = 5  # 주간 대표 기사(태그 많은 순)

def parse_ymd(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

def safe_list(x):
    return x if isinstance(x, list) else []

def main():
    if not ALL_JSON_PATH.exists():
        print(f"[WARN] {ALL_JSON_PATH} 없음")
        WEEKLY_JSON_PATH.write_text(json.dumps({}, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    all_items = json.loads(ALL_JSON_PATH.read_text(encoding="utf-8")) or []

    # 1) 날짜 파싱 가능한 것만
    parsed = []
    for a in all_items:
        d = parse_ymd(str(a.get("date", "")).strip())
        if not d:
            continue
        parsed.append((d, a))

    if not parsed:
        print("[WARN] all.json에 날짜 파싱 가능한 데이터가 없음")
        WEEKLY_JSON_PATH.write_text(json.dumps({}, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    # 2) 기준일: all.json의 '최신 날짜'를 기준으로 최근 7일 구간 산정(크롤링 실행 시간이 들쭉날쭉해도 안정적)
    latest_date = max(d for d, _ in parsed)
    start_date = latest_date - timedelta(days=DAYS - 1)

    week_items = [a for d, a in parsed if start_date <= d <= latest_date]

    # 3) 집계
    by_source = Counter()
    tag_counter = Counter()
    by_day = Counter()

    for a in week_items:
        by_source[a.get("source", "미상")] += 1
        by_day[a.get("date")] += 1
        for t in safe_list(a.get("tags")):
            tag_counter[t] += 1

    top_keywords = [{"tag": t, "count": c} for t, c in tag_counter.most_common(TOP_TAGS)]
    sources = [{"source": s, "count": c} for s, c in by_source.most_common()]

    # 대표 기사: 태그 많은 순 → 중요도(is_important) → 최신일자 → 제목
    def art_key(a):
        tags_len = len(safe_list(a.get("tags")))
        imp = int(a.get("is_important", 0) or 0)
        date_s = str(a.get("date") or "")
        title = str(a.get("title") or "")
        return (tags_len, imp, date_s, title)

    top_articles = sorted(week_items, key=art_key, reverse=True)[:TOP_ARTICLES]
    top_articles = [{
        "date": a.get("date"),
        "source": a.get("source"),
        "title": a.get("title"),
        "url": a.get("url"),
        "tags": safe_list(a.get("tags"))[:10],  # 너무 길면 10개까지만
    } for a in top_articles]

    # 4) 한줄 요약(룰 기반)
    # - 1위 키워드 + 신문사 비중 + 기사량 증감(주간 내 피크일)
    one_liner = ""
    if top_keywords:
        top1 = top_keywords[0]["tag"]
        peak_day, peak_cnt = ("", 0)
        if by_day:
            peak_day, peak_cnt = max(by_day.items(), key=lambda x: x[1])
        main_source, main_cnt = ("", 0)
        if sources:
            main_source, main_cnt = sources[0]["source"], sources[0]["count"]
        one_liner = f"이번 주는 ‘{top1}’ 이슈가 가장 두드러졌고, {main_source} 비중이 높았으며({main_cnt}건), 기사량 피크는 {peak_day}({peak_cnt}건)입니다."

    weekly = {
        "range": {"from": start_date.strftime("%Y-%m-%d"), "to": latest_date.strftime("%Y-%m-%d")},
        "total": len(week_items),
        "by_source": sources,
        "top_keywords": top_keywords,
        "by_day": [{"date": d, "count": c} for d, c in sorted(by_day.items())],
        "top_articles": top_articles,
        "one_liner": one_liner
    }

    WEEKLY_JSON_PATH.write_text(json.dumps(weekly, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] weekly.json 생성: {WEEKLY_JSON_PATH} | total={weekly['total']} | range={weekly['range']}")

if __name__ == "__main__":
    main()
