from PIL import Image, ImageDraw, ImageFont


def make_cardnews_image(text, output_path):
    width = 1080
    height = 1350
    margin = 80

    # 배경색
    bg_color = (245, 245, 245)
    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # 폰트
    try:
        title_font = ImageFont.truetype("arial.ttf", 60)
        body_font = ImageFont.truetype("arial.ttf", 42)
    except:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    # 텍스트 박스
    draw.rectangle(
        (margin, margin, width - margin, height - margin),
        fill=(255, 255, 255),
        outline=(200, 200, 200),
        width=4
    )

    # 텍스트 나누기
    lines = []
    max_width = width - margin * 2 - 40
    for raw_line in text.split("\n"):
        line = ""
        for ch in raw_line:
            if draw.textlength(line + ch, font=body_font) < max_width:
                line += ch
            else:
                lines.append(line)
                line = ch
        lines.append(line)

    # 텍스트 그리기
    y = margin + 60
    for line in lines:
        draw.text((margin + 20, y), line, fill=(0, 0, 0), font=body_font)
        y += 60

    # ❤️ 좋아요 버튼(이미지용)
    like_text = "❤️ 좋아요"
    lw, lh = draw.textsize(like_text, font=body_font)
    lx = width - lw - 150
    ly = height - lh - 150

    draw.rectangle(
        (lx - 20, ly - 10, lx + lw + 20, ly + lh + 10),
        fill=(255, 255, 255),
        outline=(255, 100, 120),
        width=3
    )

    draw.text((lx, ly), like_text, fill=(255, 80, 90), font=body_font)

    img.save(output_path)
    print(f"[카드뉴스 생성] {output_path}")
