# -*- coding: utf-8 -*-
"""把 GBK/GB18030 编码的输出文件转成 UTF-8，方便阅读"""
import sys

src, dst = sys.argv[1], sys.argv[2]
raw = open(src, 'rb').read()
for enc in ('utf-8', 'gb18030', 'cp936'):
    try:
        text = raw.decode(enc)
        break
    except UnicodeDecodeError:
        continue
else:
    text = raw.decode('utf-8', errors='replace')
open(dst, 'w', encoding='utf-8').write(text)
print('转成 UTF-8 完成：', dst)
