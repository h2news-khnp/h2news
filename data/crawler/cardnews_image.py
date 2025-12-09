from PIL import Image, ImageDraw, ImageFont
import textwrap

def make_cardnews_image(text_list, out_path, bg_color="#1A1A1A"):
    W = H = 1080
    img = Image.new("RGB", (W, H), bg_color)
    draw = ImageDraw.Draw(img)

    font = ImageFont.truetype("arial.ttf", 42)
    margin = 80
    y = 150

    # 제목 그림 또는 아이콘
    draw.ellipse((460, 40, 620, 200), fill="#00AEEF")

    title_font = ImageFont.truetype("arial.ttf", 60)
    draw.text((margin, 230), "오늘의 수소 뉴스", fill="white", font=title_font)

    for line in text_list:
        wrapped = textwrap.fill(line, width=22)
        draw.text((margin, y), wrapped, fill="white", font=font)
        y += 200

    img.save(out_path)
    return out_path
