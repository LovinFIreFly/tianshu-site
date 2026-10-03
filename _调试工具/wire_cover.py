# -*- coding: utf-8 -*-
"""把生成好的封面图挂到剧本上（只改 img 字段，不动别的）"""
import os, sys, glob, shutil

sys.path.insert(0, r"C:\Users\junbo\Desktop\网站")
from tianshu.db import db

COVER_DIR = r"C:\Users\junbo\Desktop\网站\data\img\cover"

# 找到刚生成的图（按修改时间取最新一张）
files = [f for f in glob.glob(os.path.join(COVER_DIR, '*.png')) if os.path.isfile(f)]
if not files:
    print('没有找到生成的封面图')
    sys.exit(1)
src = max(files, key=os.path.getmtime)
target_name = 'cover-wushan.png'
dst = os.path.join(COVER_DIR, target_name)
if os.path.abspath(src) != os.path.abspath(dst):
    shutil.move(src, dst)
print('封面文件：', dst, os.path.getsize(dst), '字节')

rows = db.rows('scripts')
hit = None
for s in rows:
    if '雾山' in str(s.get('title', '')):
        hit = s
        break
if not hit:
    print('没找到「雾山夜行」，当前剧本：', [s.get('title') for s in rows][:10])
    sys.exit(1)

hit['img'] = '/img/cover/' + target_name
db.write('scripts', rows)
print('已把封面挂到《%s》-> %s' % (hit['title'], hit['img']))
