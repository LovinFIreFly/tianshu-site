# -*- coding: utf-8 -*-
"""甜薯剧本杀 · 影像素材统一调色 / 切图管线

把一个文件夹里的原始照片（手机随手拍的、素材站下的都行）批量处理成
站内 unseen 暗场版式需要的三种规格，并统一调成"近黑 + 单色低饱和"的调性。

为什么需要它：
    unseen 的"高级感"一半来自配色克制 —— 底是近黑，全站只有一个低饱和主色，
    光只出现在该亮的地方。直接把彩色照片堆上去 = 花、亮、杂 = AI 味。
    所以进来的每一张图都要先过这道"降饱和 + 压暗 + 暗角 + 冷阴影/暖高光"的调色。

三种输出（对应版式里的槽位）：
    poster  3:4.2 竖版，1200x1680  → 首页海报廊 .poster__face / 本本墙 .card__cover / 详情页 .detail__cover
    hero    16:9  横版，2560x1440  → 首屏 .stage__media-host（static/media/hero.webp）
    avatar  1:1   方图，320x320    → 头像

用法：
    python tools/media_grade.py --src 原始照片目录 --out tianshu/static/media --kind all
    python tools/media_grade.py --src a.jpg --kind hero --name hero
    python tools/media_grade.py --src 原始照片目录 --kind poster --out data/img/cover --dry-run

    # 只想看调色效果、不覆盖正式文件：
    python tools/media_grade.py --src x.jpg --kind poster --out _preview

视频（hero.mp4）用 ffmpeg，本脚本会在检测到 ffmpeg 时给出一条现成命令（见 --ffmpeg-hint）。

依赖：Pillow（本机系统 Python 3.12 自带）。不需要 ffmpeg（只有做视频才需要）。
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys

try:
    from PIL import Image, ImageChops, ImageFilter
except ImportError:
    print('需要 Pillow：用系统 Python 3.12 跑，或 pip install pillow')
    sys.exit(1)

# ---------- 三种槽位规格： (宽, 高) ----------
SPECS = {
    'poster': (1200, 1680),   # 3 : 4.2
    'hero':   (2560, 1440),   # 16 : 9
    'avatar': (320, 320),     # 1 : 1
}

# ---------- 调色参数（改这里就能整体换调性） ----------
GRADE = dict(
    sat=0.70,          # 饱和度：0.70 = 降到七成，去掉"数码鲜艳"
    contrast=1.14,     # 对比
    gamma=1.10,        # >1 = 整体压暗（暗场要暗）
    shadow=(0.010, 0.018, 0.034),   # 阴影加冷（青蓝），让暗部不死黑
    high=(0.030, 0.012, -0.004),    # 高光加暖（琥珀），呼应朱砂强调色
    lift=(0, 1, 3),    # 黑位抬一点，避免纯 0 断层
    vig=0.55,          # 暗角强度 0~1
    grain=12,          # 颗粒强度（Image.effect_noise 的 sigma，0 = 不加）
)


def _clamp(x):
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def _curve_lut():
    """按 GRADE 生成三条 256 级查找表（Pillow 的 point() 走 C，够快）。"""
    s = GRADE
    luts = []
    for c in range(3):
        table = []
        for i in range(256):
            x = i / 255.0
            x = x ** s['gamma']
            x = (x - 0.42) * s['contrast'] + 0.42
            x = _clamp(x)
            # 分离调色：阴影吃 shadow 色，高光吃 high 色
            x = x + s['shadow'][c] * (1 - x) ** 2.2 + s['high'][c] * (x ** 2.2)
            x = _clamp(x)
            # 抬黑位
            lb = s['lift'][c] / 255.0
            x = lb + x * (1 - lb)
            table.append(int(_clamp(x) * 255 + 0.5))
        luts.append(table)
    return luts


def _vignette(im, strength):
    """径向暗角：中心不动，四周压到 (1-strength)。"""
    if strength <= 0:
        return im
    w, h = im.size
    # 一条黑心白边的径向渐变，缩放到画面尺寸
    mask = Image.radial_gradient('L').resize((w, h), Image.BILINEAR)
    # mask: 中心 0 → 边缘 255。转成"乘法系数"：中心 1，边缘 (1-strength)
    floor = int(255 * (1 - strength))
    mask = mask.point(lambda v: floor + (255 - floor) * v // 255)
    return ImageChops.multiply(im, Image.merge('RGB', (mask, mask, mask)))


def grade(im, spec):
    """核心：一张原始图 → 暗场调性。"""
    s = GRADE
    w, h = spec
    # 等比放大到刚好盖住目标框，再居中裁 —— 不变形
    im = im.convert('RGB')
    src_ratio = im.width / im.height
    dst_ratio = w / h
    if src_ratio > dst_ratio:                 # 原图更宽 → 以高为准
        nw = int(h * src_ratio)
        im = im.resize((nw, h), Image.LANCZOS)
        left = (nw - w) // 2
        im = im.crop((left, 0, left + w, h))
    else:                                     # 原图更高 → 以宽为准
        nh = int(w / src_ratio)
        im = im.resize((w, nh), Image.LANCZOS)
        top = int((nh - h) * 0.42)            # 略偏上，人像/主体通常在偏上
        im = im.crop((0, top, w, top + h))

    # 1) 降饱和
    if s['sat'] < 1:
        g = im.convert('L')
        im = Image.blend(im, Image.merge('RGB', (g, g, g)), 1 - s['sat'])

    # 2) 曲线 + 分离调色
    luts = _curve_lut()
    im = Image.merge('RGB', [ch.point(luts[i]) for i, ch in enumerate(im.split())])

    # 3) 暗角
    im = _vignette(im, s['vig'])

    # 4) 细颗粒（胶片感，不是数码噪点）
    if s['grain'] > 0:
        noise = Image.effect_noise(im.size, s['grain']).convert('RGB')
        im = Image.blend(im, ImageChops.overlay(im, noise), 0.18)
    return im


def save(im, out_dir, name, kind):
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, name)
    written = []
    try:
        p = base + '.webp'
        im.save(p, 'WEBP', quality=82, method=6)
        written.append(p)
    except Exception as e:                     # 老 Pillow 没有 webp 就退回 jpg
        print('  webp 存不了（%s），改存 jpg' % e)
    p2 = base + '.jpg'
    im.save(p2, 'JPEG', quality=86, optimize=True, progressive=True)
    written.append(p2)
    return written


def ffmpeg_hint(src, out_dir):
    """给出手工做 hero.mp4 的命令（本机若没 ffmpeg 就只打印）。"""
    cmd = ('ffmpeg -i "%s" -t 8 -an -vf "scale=2560:1440:force_original_aspect_ratio=increase,'
           'crop=2560:1440,eq=saturation=0.7:contrast=1.14:brightness=-0.08,'
           'vignette=PI/5,noise=alls=8:allf=t" '
           '-c:v libx264 -pix_fmt yuv420p -crf 26 -movflags +faststart "%s/hero.mp4"'
           % (src, out_dir))
    return cmd


def main():
    ap = argparse.ArgumentParser(description='甜薯 · 影像素材调色/切图')
    ap.add_argument('--src', required=True, help='原始图片文件或目录')
    ap.add_argument('--out', default='tianshu/static/media', help='输出目录')
    ap.add_argument('--kind', default='all', choices=['poster', 'hero', 'avatar', 'all'])
    ap.add_argument('--name', default='', help='单文件时的输出名（不含扩展名）')
    ap.add_argument('--dry-run', action='store_true', help='只打印将要做什么')
    ap.add_argument('--ffmpeg-hint', action='store_true', help='只打印做视频的 ffmpeg 命令')
    args = ap.parse_args()

    if args.ffmpeg_hint:
        print(ffmpeg_hint(args.src, args.out))
        return

    files = []
    if os.path.isdir(args.src):
        for ext in ('*.jpg', '*.jpeg', '*.png', '*.webp', '*.bmp', '*.tif', '*.tiff'):
            files += glob.glob(os.path.join(args.src, ext))
            files += glob.glob(os.path.join(args.src, ext.upper()))
        files.sort()
    else:
        files = [args.src]
    if not files:
        print('没找到图片：', args.src)
        return

    kinds = list(SPECS) if args.kind == 'all' else [args.kind]
    print('待处理 %d 张 → %s' % (len(files), ' / '.join(kinds)))
    for f in files:
        stem = args.name or os.path.splitext(os.path.basename(f))[0]
        for kind in kinds:
            sub = '' if kind == 'hero' else kind
            out_dir = os.path.join(args.out, sub) if sub else args.out
            name = 'hero' if kind == 'hero' else stem
            if args.dry_run:
                print('  [dry] %s → %s/%s.%s  %s' % (f, out_dir, name, 'webp', SPECS[kind]))
                continue
            try:
                im = Image.open(f)
                im.load()
                out = grade(im, SPECS[kind])
                written = save(out, out_dir, name, kind)
                print('  ✓ %s → %s' % (os.path.basename(f), ', '.join(os.path.relpath(p) for p in written)))
            except Exception as e:
                print('  ✗ %s：%s' % (os.path.basename(f), e))
    print('\n视频（hero.mp4）需要 ffmpeg，命令：')
    print('  ' + ffmpeg_hint(files[0], args.out))


if __name__ == '__main__':
    main()
