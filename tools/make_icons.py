# -*- coding: utf-8 -*-
"""生成甜薯剧本杀的 App 图标（字标方案）。

为什么不用 AI 生图：字形要工整、颜色要精确、缩到 24px 也得清楚 —— 手绘矢量才做得到，
AI 出的一是带水印、二是笔画常有畸变（"薯"字尤其容易糊）。

设计依据（见 docs 那份《值得学习的手机App图标设计Top10》）：
  · Revolut（第 8 名）：白底 + 单一粗体字标 = 极简高级，符号包围盒约 37%，大留白
  · 原则① 单一核心符号：整张图只有一个「薯」字，没有第二个视觉焦点
  · 原则② 三色以内：纸 #F4F1EA / 朱 #C8321E / （备用墨 #141312）
  · 原则③ 小尺寸可辨：字标笔画粗、无细装饰，24px 仍是清晰剪影
  · 原则④ 形状优先：先看"朱红印章 + 一个字"的剪影，再看细节
  · maskable 安全区：manifest 里 purpose 是 "any maskable"，安卓会按中心 80% 的圆裁切，
    所以印章方框控制在画布 56%（对角线 39.6% < 安全半径 40%），边角不会被切掉。

输出：
  static/icon.svg                    favicon（矢量，浏览器标签页用）
  static/icons/icon-512.png          安装/启动图标
  static/icons/icon-192.png
  static/icons/apple-touch-icon.png  180×180（iPhone 加到桌面用）
另在 _icon-preview/ 生成红底版供对比（默认不采用）。
"""
import os

from PIL import Image, ImageDraw, ImageFont

PAPER = (244, 241, 234)      # 纸 #F4F1EA
VERMILION = (200, 50, 30)    # 朱 #C8321E
INK = (20, 19, 18)           # 墨 #141312

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GLYPH = '薯'

# 中文字体候选（Windows 优先微软雅黑粗体；Linux 上退到思源/文泉驿，没有就用默认）
_FONTS = [
    r'C:\Windows\Fonts\msyhbd.ttc',          # 微软雅黑 Bold
    r'C:\Windows\Fonts\Dengb.ttf',           # 等线 Bold
    r'C:\Windows\Fonts\msyh.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
]


def load_font(px):
    for p in _FONTS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, px)
            except Exception:
                continue
    return ImageFont.load_default()


def draw(variant, size):
    """画一张图标。variant: 'stamp' = 纸底+朱红印章+纸色字；'solid' = 朱红满版+纸色字"""
    img = Image.new('RGB', (size, size), PAPER if variant == 'stamp' else VERMILION)
    d = ImageDraw.Draw(img)

    if variant == 'stamp':
        side = int(round(size * 0.56))                 # maskable 安全区内在
        pad = (size - side) // 2
        d.rounded_rectangle([pad, pad, pad + side, pad + side],
                            radius=int(side * 0.2), fill=VERMILION)
        glyph_px = int(round(size * 0.30))
    else:
        glyph_px = int(round(size * 0.40))

    font = load_font(glyph_px)
    # anchor='mm' 以字形的视觉中心对齐（不同字体的基线不一样，用 bbox 量出来更准）
    box = d.textbbox((0, 0), GLYPH, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text((size / 2 - box[0] - w / 2, size / 2 - box[1] - h / 2), GLYPH,
           font=font, fill=PAPER)
    return img


def main():
    icons = os.path.join(ROOT, 'tianshu', 'static', 'icons')
    prev = os.path.join(ROOT, '_icon-preview')
    os.makedirs(icons, exist_ok=True)
    os.makedirs(prev, exist_ok=True)

    for size, name in [(512, 'icon-512.png'), (192, 'icon-192.png'),
                       (180, 'apple-touch-icon.png')]:
        draw('stamp', size).save(os.path.join(icons, name))
        print('  %-22s %d×%d  纸底+朱红印章+「薯」' % (name, size, size))

    draw('stamp', 512).save(os.path.join(prev, 'A-字标-纸底印章.png'))
    draw('solid', 512).save(os.path.join(prev, 'B-字标-朱红满版.png'))
    print('  对比稿放在 _icon-preview/（A 已采用，B 备用）')

    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <!-- 甜薯剧本杀 · 字标：纸底 + 朱红印章 + 一个「薯」字（Revolut 式极简）
       三色以内（纸 #F4F1EA / 朱 #C8321E），单一符号，24px 仍可辨 -->
  <rect width="64" height="64" fill="#F4F1EA"/>
  <rect x="14.1" y="14.1" width="35.8" height="35.8" rx="7.2" fill="#C8321E"/>
  <text x="32" y="32" fill="#F4F1EA" font-size="19.2" font-weight="700"
        text-anchor="middle" dominant-baseline="central"
        font-family="PingFang SC,Microsoft YaHei,Hiragino Sans GB,Noto Sans CJK SC,WenQuanYi Zen Hei,sans-serif">薯</text>
</svg>
'''
    with open(os.path.join(ROOT, 'tianshu', 'static', 'icon.svg'), 'w',
              encoding='utf-8', newline='\n') as f:
        f.write(svg)
    print('  icon.svg                矢量 favicon（已重写）')


if __name__ == '__main__':
    main()
