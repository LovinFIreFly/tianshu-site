# -*- coding: utf-8 -*-
"""把 data/img/ 里所有占位小图（初始化写的 1x1 透明 PNG）换成真图。

- cover  ← tools/img-pool/ 场景海报 + mobile/poster-n01|n02.jpg
- avatar/dm/role ← tools/img-pool/ 人物插画
- qr     ← Pillow 画的「群二维码待更新」说明图（不放头像，避免误导）

所有图统一缩到最长边 900px 再存（JPG 86 / PNG 压缩），避免 1MB+ 大图拖慢手机。
同一文件名永远得到同一张图（按名字哈希稳定分配）。

用法：python tools/fix_imgs.py [--all]   # 不带 --all 只填 <=200 字节的占位
"""
import glob
import hashlib
import io
import os
import sys

from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POOL = os.path.join(BASE, 'tools', 'img-pool')
IMG = os.path.join(BASE, 'data', 'img')
PLACEHOLDER_SIZE = 200


def pool_for(sub):
    files = glob.glob(os.path.join(POOL, '*'))
    if sub == 'cover':
        scenes = [f for f in files if not any(k in os.path.basename(f) for k in ('头像',))]
        posters = [os.path.join(BASE, 'mobile', 'poster-n01.jpg'),
                   os.path.join(BASE, 'mobile', 'poster-n02.jpg')]
        return scenes + posters
    if sub == 'qr':
        return []                       # qr 特殊处理
    return [f for f in files if '头像' in os.path.basename(f)] or files


def to_bytes(src, ext, px=900):
    """照片类内容统一压成 JPEG 字节（~200KB 级）。浏览器对图片按内容嗅探，
    即使扩展名是 .png 也能正常显示；换来的是体积小 5 倍，手机加载不拖。"""
    im = Image.open(src).convert('RGB')
    im.thumbnail((px, px))
    buf = io.BytesIO()
    im.save(buf, 'JPEG', quality=82, optimize=True)
    return buf.getvalue()


def qr_placeholder(ext):
    """一张说明图：群二维码待更新，联系店家"""
    im = Image.new('RGB', (600, 600), (241, 237, 228))
    d = ImageDraw.Draw(im)
    ink = (23, 20, 15)
    d.rectangle([20, 20, 579, 579], outline=ink, width=3)
    for i in range(3):
        d.rectangle([40 + i, 40 + i, 559 - i, 559 - i], outline=(214, 207, 192), width=1)
    d.rectangle([200, 200, 400, 400], outline=ink, width=3)
    d.line([200, 200, 400, 400], fill=ink, width=3)
    d.line([400, 200, 200, 400], fill=ink, width=3)
    try:
        from PIL import ImageFont
        font = ImageFont.truetype('msyh.ttc', 30)
        small = ImageFont.truetype('msyh.ttc', 22)
    except Exception:
        font = small = None
    d.text((300, 450), '群二维码待更新', fill=ink, anchor='mm', font=font)
    d.text((300, 500), '加店家微信进群', fill=(107, 101, 89), anchor='mm', font=small)
    buf = io.BytesIO()
    if ext in ('jpg', 'jpeg'):
        im.save(buf, 'JPEG', quality=86)
    else:
        im.save(buf, 'PNG', optimize=True)
    return buf.getvalue()


def main():
    force = '--all' in sys.argv
    total = 0
    for sub in ('cover', 'avatar', 'dm', 'role', 'qr', 'shop'):
        folder = os.path.join(IMG, sub)
        if not os.path.isdir(folder):
            continue
        pool = pool_for(sub)
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            ext = name.rsplit('.', 1)[-1].lower()
            if ext not in ('png', 'jpg', 'jpeg', 'webp'):
                continue
            size = os.path.getsize(path)
            if not force and size > PLACEHOLDER_SIZE:
                continue
            if sub == 'qr' or not pool:
                data = qr_placeholder('jpg')
                src = '(qr placeholder)'
            else:
                h = int(hashlib.md5(name.encode()).hexdigest(), 16)
                src = pool[h % len(pool)]
                data = to_bytes(src, ext)
                src = os.path.basename(src)[:24]
            with open(path, 'wb') as f:
                f.write(data)
            print('filled %-8s %-28s %5d -> %6d  %s' % (sub, name, size, len(data), src))
            total += 1
    print('done: %d files' % total)


if __name__ == '__main__':
    main()
