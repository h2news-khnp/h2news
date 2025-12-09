from PIL import Image, ImageDraw, ImageFont
import textwrap


# ------------------------------------
# 기본 설정
# ------------------------------------

CARD_WIDTH = 1080
CARD_HEIGHT = 1350
MARGIN = 80

# 폰트 설정 (GitHub Actions에서도 깨지지 않도록 기본 폰트 사용)
TITLE_FONT_SIZE = 60
BODY_FONT_SIZE = 40


# ------------------------------------
# 1. 자동 줄바꿈 함수
# ------------------------------------

def wrap_text(text, font, max_width):
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        wrapped = textwrap.wrap(paragraph, width=40)
        lines.extend(wrapped)
    return lines


# ------------------------------------
# 2. 카드뉴스 이미지 생성 함수
# ------------------------------------

def make_cardnews_image(title, summary, save_path):
    """
    title : 기사 제목
    summary : 3줄 요약 텍스트
    save_path : 저장될 이미지 경로 (예: data/2025-01-01_1.png)
    """

    # 캔버스 생성
    img = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 폰트 로딩 (기본 폰트 사용)
    title_font = ImageFont.truetype("arial.ttf", TITLE_FONT_SIZE) if "arial.ttf" else ImageFont.load_default()
    body_font = ImageFont.truetype("arial.ttf", BODY_FONT_SIZE) if "arial.ttf" else ImageFont.load_default()

    y = MARGIN

    # -----------------------------
    # 제목 그리기 (자동 줄바꿈)
    # -----------------------------
    title_lines = wrap_text(title, title_font, CARD_WIDTH - MARGIN * 2)

    for line in title_lines:
        draw.text((MARGIN, y), line, font=title_font, fill=(0, 0, 0))
        y += TITLE_FONT_SIZE + 10

    y += 30  # 제목과 본문 간 여백

    # -----------------------------
    # 본문(3줄 요약) 출력
    # -----------------------------
    summary_lines = wrap_text(summary, body_font, CARD_WIDTH - MARGIN * 2)

    for line in summary_lines:
        draw.text((MARGIN, y), line, font=body_font, fill=(50, 50, 50))
        y += BODY_FONT_SIZE + 8

    # -----------------------------
    # 파일 저장
    # -----------------------------
    img.save(save_path)
    print(f"🖼 카드뉴스 생성 완료 → {save_path}")
