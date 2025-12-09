from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import textwrap
import random

# -----------------------------
# 공통 유틸: textbbox로 텍스트 크기 구하기
# -----------------------------
def get_text_size(draw, text, font):
    """
    Pillow 최신버전에서 textsize() 제거 → textbbox()로 대체
    """
    if not text:
        return 0, 0
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    return w, h


def wrap_text(text, width):
    """
    아주 단순한 문자 개수 기준 줄바꿈 (한글·이모지 섞여도 동작)
    """
    if not text:
        return []
    # textwrap이 공백 기준이라, 공백이 거의 없으면 강제 슬라이스
    if " " not in text and len(text) > width:
        return [text[i:i+width] for i in range(0, len(text), width)]
    return textwrap.wrap(text, width=width)


def load_font(size: int):
    """
    GitHub Actions 환경에서도 돌아가도록:
    1순위: DejaVuSans
    2순위: 기본 폰트
    """
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except:
        try:
            # Ubuntu 계열 기본 설치 경로 시도
            return ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size
            )
        except:
            return ImageFont.load_default()


def make_cardnews_image(card_text: str, out_path):
    """
    card_text: "제목\n\n요약본문..." 형태 문자열
    out_path: 저장할 경로 (str 또는 Path)
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # --- 캔버스 기본 설정 (정사각형 카드) ---
    W, H = 900, 900
    img = Image.new("RGB", (W, H), "#101018")
    draw = ImageDraw.Draw(img)

    title_font = load_font(40)
    body_font = load_font(28)
    small_font = load_font(22)

    # 상단 배너용 그라데이션 느낌 (단색으로 대체)
    header_h = 150
    draw.rectangle([0, 0, W, header_h], fill="#141b3f")

    # 살짝 라운드 박스 느낌의 카드 영역
    margin = 60
    card_top = header_h - 20
    card_bottom = H - margin
    draw.rounded_rectangle(
        [margin, card_top, W - margin, card_bottom],
        radius=40,
        outline="#333955",
        width=3,
        fill="#15192a",
    )

    # 상단 로고 / 라벨 영역
    label_text = "⚡ H2 DAILY BRIEF"
    lw, lh = get_text_size(draw, label_text, font=small_font)
    draw.text(
        ((W - lw) // 2, 40),
        label_text,
        font=small_font,
        fill="#9fd5ff",
    )

    # 날짜 뱃지
    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d")
    date_text = f"🗓 {today_str}"
    dw, dh = get_text_size(draw, date_text, font=small_font)
    draw.rounded_rectangle(
        [W - dw - 40, header_h - dh - 10, W - 30, header_h + 10],
        radius=16,
        fill="#1f2648",
    )
    draw.text(
        (W - dw - 35, header_h - dh), date_text, font=small_font, fill="#b8c7ff"
    )

    # --- card_text 분리: 첫 줄 = 제목, 나머지 = 요약 ---
    lines = [ln for ln in card_text.splitlines() if ln.strip()]
    if not lines:
        lines = ["제목 없음", "내용 없음"]

    title = lines[0].strip()
    body_text = " ".join(line.strip() for line in lines[1:]) if len(lines) > 1 else ""

    # 제목에 아이콘 하나 추가
    title_icon_candidates = ["🔋", "🌱", "🚀", "⚙️", "🏭", "📊", "🛰️"]
    icon = random.choice(title_icon_candidates)
    title = f"{icon} {title}"

    # --- 제목 렌더링 ---
    y = card_top + 40
    title_wrap = wrap_text(title, width=16)  # 글자수 기준 대략 감으로

    for t_line in title_wrap:
        tw, th = get_text_size(draw, t_line, font=title_font)
        draw.text(
            (margin + 30, y),
            t_line,
            font=title_font,
            fill="#ffffff",
        )
        y += th + 8

    # 제목과 본문 사이 구분선
    y += 10
    draw.line([margin + 20, y, W - margin - 20, y], fill="#303754", width=2)
    y += 20

    # --- 요약 본문 렌더링 ---
    if body_text:
        body_wrap = wrap_text(body_text, width=24)
        max_body_lines = 6  # 카드 안에 들어갈 최대 줄 수
        body_wrap = body_wrap[:max_body_lines]

        for b_line in body_wrap:
            bw, bh = get_text_size(draw, b_line, font=body_font)
            draw.text(
                (margin + 30, y),
                b_line,
                font=body_font,
                fill="#e3e7ff",
            )
            y += bh + 6

    # 하단 태그/푸터 영역
    footer_y = card_bottom - 90
    draw.line(
        [margin + 20, footer_y, W - margin - 20, footer_y], fill="#303754", width=1
    )

    footer_left = "💡 수소·연료전지 오늘의 한 장 카드뉴스"
    flw, flh = get_text_size(draw, footer_left, font=small_font)
    draw.text(
        (margin + 30, footer_y + 20),
        footer_left,
        font=small_font,
        fill="#9ca7ff",
    )

    # 우측 하단 작은 로고 느낌
    footer_right = "MKAY·H2 Watcher"
    frw, frh = get_text_size(draw, footer_right, font=small_font)
    draw.text(
        (W - margin - 30 - frw, footer_y + 20),
        footer_right,
        font=small_font,
        fill="#6b76c9",
    )

    # 파일 저장
    img.save(out_path, format="PNG")
    print(f"[CARD] 카드뉴스 생성 완료 → {out_path}")
