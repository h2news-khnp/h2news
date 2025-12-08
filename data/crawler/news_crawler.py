import json
from datetime import datetime
from pathlib import Path

def main():
    # 오늘 날짜 기준 파일명 만들기 (예: 2025-12-09.json)
    today = datetime.now().strftime("%Y-%m-%d")
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    sample_data = [
        {
            "date": today,
            "source": "예시 매체",
            "title": f"{today} 수소 뉴스 자동 생성 예시",
            "url": "https://example.com/sample",
            "summary": "이 데이터는 크롤링 테스트용으로 파이썬 스크립트가 자동 생성한 예시입니다.",
            "tags": ["테스트", "자동화"]
        }
    ]

    out_file = data_dir / f"{today}.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(sample_data, f, ensure_ascii=False, indent=2)

    print(f"생성 완료: {out_file}")

if __name__ == "__main__":
    main()
