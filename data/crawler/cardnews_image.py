from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from pathlib import Path
import textwrap


# -----------------------------
# 1. 폰트 로딩 유틸
# -----------------------------

def _load_font(size: int):
    """
    환경에 따라 폰트가 다르기 때문에, 여러 후보를 순차적으로 시도.
    하나도 없으면 Pillow 기본폰트 사용.
    """
    font_candidates = [
        # 리눅스/서버에 있을 수 있는 한글 폰트들
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumSquare.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        # 윈도우 / 맥에서 로컬 테스트용
        "NanumGothic.ttf",
        "NanumSquare.ttf",
        "Malgun.ttf",
        "malgun.ttf",
        "AppleGothic.ttf",
        "Arial Unicode.ttf",
        "arial.ttf",
    ]

    for path in font_candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            continue

    # 폰트를 못 찾으면 기본 폰트
    return ImageFont.load_default()


# -----------------------------
# 2. 텍스트 래핑 유틸
# -----------------------------

def _wrap_korean(text: str, width: int) -> str:
    """
    한글 + 영어 섞인 문장을 대략적인 글자 수 기준으로 줄바꿈.
    (픽셀 단위가 아니고 문자 수 기준이라 약간 오차는 있지만 실용성은 충분)
    """
    text = (text or "").strip()
    if not text:
        return ""

    lines = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        # textwrap.wrap은 공백 기준이라 한글엔 약하지만,
        # 대략적인 width로 잘려도 카드뉴스 용도로는 충분하다.
        wrapped = textwrap.wrap(paragraph, width=width)
        if not wrapped:
            continue
        lines.extend(wrapped)

    return "\n".join(lines)


# -----------------------------
# 3. 메인: 카드뉴스 이미지 생성
# -----------------------------

def make_cardnews_image(lines, out_path: str, size=(800, 800)):
    """
    lines: ['제목', '요약1', '요약2', '요약3', ...] 형태의 문자열 리스트
    out_path: 저장할 이미지 경로 (예: 'data/cardnews/2025-12-09_0.png')
    """

    # 안전장치
    if not lines:
        lines = ["수소·연료전지 뉴스", "오늘의 수소 뉴스 요약", "데이터가 부족합니다."]

    title_text = str(lines[0])
    body_lines = [str(x) for x in lines[1:]] if len(lines) > 1 else []

    # 이미지 캔버스
    width, height = size
    img = Image.new("RGB", size, (10, 14, 30))  # 진한 남색 배경
    draw = ImageDraw.Draw(img)

    # 폰트
    title_font = _load_font(42)
    body_font = _load_font(28)
    meta_font = _load_font(22)

    # 카드(라운드 박스) 영역
    margin = 60
    card_radius = 40
    card_box = (margin, margin, width - margin, height - margin)

    # 라운드 사각형 (배경 카드)
    try:
        draw.rounded_rectangle(card_box, radius=card_radius, fill=(20, 28, 60))
    except Exception:
        # rounded_rectangle이 없는 Pillow 버전 대비
        draw.rectangle(card_box, fill=(20, 28, 60))

    # 상단 장식 이모지 바
    emoji_bar = "🔋🌱⚡ 수소·연료전지 TODAY ⚡🌱🔋"
    eb_w, eb_h = draw.textsize(emoji_bar, font=meta_font)
    eb_x = (width - eb_w) // 2
    eb_y = margin + 18
    draw.text((eb_x, eb_y), emoji_bar, font=meta_font, fill=(180, 220, 255))

    # 제목 영역
    title_max_width_chars = 18
    wrapped_title = _wrap_korean(title_text, width=title_max_width_chars)

    # 제목 위치 계산
    title_y_start = eb_y + eb_h + 24
    # 왼쪽 정렬 카드 내부 여백
    text_left = margin + 40

    # 제목 여러 줄 출력
    y = title_y_start
    for line in wrapped_title.split("\n"):
        draw.text((text_left, y), line, font=title_font, fill=(255, 255, 255))
        _, line_h = draw.textsize(line, font=title_font)
        y += line_h + 6

    # 제목 아래 얇은 라인
    line_y = y + 8
    draw.line(
        [(text_left, line_y), (width - margin - 40, line_y)],
        fill=(90, 130, 230),
        width=3,
    )
    y = line_y + 20

    # 본문(요약 3줄) 영역
    body_max_width_chars = 26
    bullet_emojis = ["✅", "🔹", "📌", "➕", "⭐"]

    for idx, raw_line in enumerate(body_lines):
        if not raw_line.strip():
            continue
        wrapped = _wrap_korean(raw_line, width=body_max_width_chars)
        bullet = bullet_emojis[idx % len(bullet_emojis)]

        for j, line in enumerate(wrapped.split("\n")):
            prefix = f"{bullet} " if j == 0 else "   "
            draw.text(
                (text_left, y),
                prefix + line,
                font=body_font,
                fill=(220, 230, 255),
            )
            _, line_h = draw.textsize(prefix + line, font=body_font)
            y += line_h + 6

        # 줄 간 간격
        y += 8

    # 하단 메타 정보 (날짜)
    today_str = datetime.now().strftime("%Y-%m-%d")
    meta_text = f"🗓 {today_str} · H2 뉴스 자동요약"
    mw, mh = draw.textsize(meta_text, font=meta_font)
    meta_x = width - margin - 40 - mw
    meta_y = height - margin - 40
    draw.text((meta_x, meta_y), meta_text, font=meta_font, fill=(160, 180, 220))

    # 저장 경로 생성
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG")
    print(f"[카드뉴스] 이미지 생성 완료 → {out_path}")
