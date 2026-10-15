# -*- coding: utf-8 -*-
"""静态资源的「交付时」压缩：注释与缩进不进浏览器。

本项目的 CSS/JS 里刻意写了大量**设计来由 / 踩坑记录**注释 —— 这是有价值的文档资产，
但对浏览器毫无用处；而且中文注释几乎压不动，gzip 后**注释占了 CSS 体积的一半以上**
（实测 unseen.css gzip 32.4K → 去注释后 15.7K）。

所以策略是：**源文件保持带注释**（人和后续维护都靠它），**由本模块在发送时**去掉注释/缩进。
压缩是保守的，只去注释 + 折叠空白，**不做标识符混淆、不动标点**，把语义风险降到零：
  · CSS：去 /* */ 块注释，再把连续空白折叠成单个空格。
  · JS ：去 /* */ 与「整行 //」注释，**保留换行**（绝不碰分号自动插入规则）。

缓存按源文件 mtime，源文件一改立即生效 —— 不存在"改了没更新"的陈旧副本问题。
"""
import os
import re
import threading

_lock = threading.Lock()
_cache = {}                      # relpath -> (mtime, stripped_text)

_CSS_BLOCK = re.compile(r'/\*.*?\*/', re.S)
_JS_BLOCK = re.compile(r'/\*.*?\*/', re.S)
_WS = re.compile(r'\s+')


def strip_css(text):
    return _WS.sub(' ', _CSS_BLOCK.sub('', text)).strip()


def strip_js(text):
    text = _JS_BLOCK.sub('', text)
    keep = []
    for line in text.split('\n'):
        if line.strip().startswith('//'):        # 只去"整行注释"，绝不截断行尾（URL 里的 // 会误伤）
            continue
        keep.append(line.rstrip())
    return '\n'.join(keep).strip()


def minified(site_dir, relpath):
    """返回 relpath 压缩后的文本（css/js）；其他类型原样返回；文件不存在返回 None。"""
    path = os.path.join(site_dir, relpath)
    try:
        mt = os.stat(path).st_mtime
    except OSError:
        return None
    with _lock:
        hit = _cache.get(relpath)
        if hit and hit[0] == mt:
            return hit[1]
    try:
        with open(path, encoding='utf-8') as fh:
            src = fh.read()
    except OSError:
        return None
    if relpath.endswith('.css'):
        out = strip_css(src)
    elif relpath.endswith('.js'):
        out = strip_js(src)
    else:
        out = src
    with _lock:
        _cache[relpath] = (mt, out)
    return out
