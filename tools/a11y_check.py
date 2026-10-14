# -*- coding: utf-8 -*-
"""静态无障碍检查（不依赖浏览器，可直接挂 CI）。

对着**已渲染的 HTML** 检查一批高信号规则（等价于 axe 里不需要布局的那几条）：
  · <html lang> 是否声明
  · <img> 是否都有 alt（装饰图可为空 alt=""）
  · 表单控件是否都有可访问名（label[for] / aria-label / aria-labelledby）
  · 图标类 <a>/<button> 是否都有文字或 aria-label
  · 页内 id 是否重复
  · 标题层级是否跳跃 / 每页是否只有一个 h1
  · 是否有 main / nav 地标
  · 是否有"跳到主内容"（.skip）

用法：
    python tools/a11y_check.py                      # 默认连 http://127.0.0.1:8081
    python tools/a11y_check.py http://127.0.0.1:8120
    python tools/a11y_check.py <base> --strict      # 有 violation 就 exit 1
"""
import sys
import io
import re
from html.parser import HTMLParser
from urllib.request import urlopen

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PAGES = ['/', '/?browse=1', '/scripts', '/login', '/register', '/forgot', '/car', '/comm', '/group', '/faq']

# 这些控件类型不需要 label
NO_LABEL_TYPES = {'hidden', 'submit', 'button', 'reset', 'image'}
# 允许空的可访问名（纯图标由 aria-label 提供，这里只判"有没有"）


class Audit(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang = None
        self.imgs = []          # (has_alt: bool)
        self.controls = []      # dict(tag,name,id,type,aria)
        self.label_for = set()
        self.ids = []           # all id attrs (for duplicate detection)
        self.headings = []      # levels
        self.has_main = False
        self.has_nav = False
        self.skip = False
        self._in_label = 0
        self._a_stack = []      # anchors being parsed: {'text':str,'aria':str|None,'href':str|None,'cls':str}
        self._btn_stack = []
        self.bad_links = []     # icon/empty links without aria
        self.bad_buttons = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'html' and self.lang is None:
            self.lang = a.get('lang')
        if 'id' in a and a['id']:
            self.ids.append(a['id'])
        if tag == 'main':
            self.has_main = True
        if tag == 'nav':
            self.has_nav = True
        if tag == 'img':
            self.imgs.append('alt' in a)
        m = re.match(r'^h([1-6])$', tag)
        if m:
            self.headings.append(int(m.group(1)))
        if tag in ('input', 'select', 'textarea'):
            self.controls.append({'tag': tag, 'name': a.get('name', ''), 'id': a.get('id', ''),
                                  'type': (a.get('type') or '').lower(),
                                  'aria': a.get('aria-label') or a.get('aria-labelledby'),
                                  'wrapped': self._in_label > 0})   # <label> 包裹式关联也有效
        if tag == 'label':
            self._in_label += 1
            if a.get('for'):
                self.label_for.add(a['for'])
        if re.search(r'(^|\s)skip(\s|$)', a.get('class', '') or ''):
            self.skip = True
        if tag == 'a':
            self._a_stack.append({'text': '', 'aria': a.get('aria-label'), 'href': a.get('href'), 'cls': a.get('class', '')})
        if tag == 'button':
            self._btn_stack.append({'text': '', 'aria': a.get('aria-label')})

    def handle_endtag(self, tag):
        if tag == 'a' and self._a_stack:
            el = self._a_stack.pop()
            txt = el['text'].strip()
            # 不含图片/仅图标链接：没文字又没 aria-label 就算无访问名
            if not txt and not el['aria'] and el['href'] and el['href'] != '#':
                self.bad_links.append(el['href'])
        if tag == 'button' and self._btn_stack:
            el = self._btn_stack.pop()
            if not el['text'].strip() and not el['aria']:
                self.bad_buttons.append('button')
        if tag == 'label':
            self._in_label = max(0, self._in_label - 1)

    def handle_data(self, data):
        if self._a_stack:
            self._a_stack[-1]['text'] += data
        if self._btn_stack:
            self._btn_stack[-1]['text'] += data


def check(base, path):
    html = urlopen(base + path, timeout=10).read().decode('utf-8', 'replace')
    au = Audit()
    au.feed(html)
    v = []
    if not au.lang:
        v.append('html 缺少 lang 属性')
    if not au.has_main:
        v.append('缺少 <main> 地标')
    if not au.has_nav:
        v.append('缺少 <nav> 地标')
    if not au.skip:
        v.append('缺少"跳到主内容"(.skip)')
    no_alt = sum(1 for ok in au.imgs if not ok)
    if no_alt:
        v.append('%d 个 <img> 缺 alt' % no_alt)
    # 控件可访问名
    miss = []
    for c in au.controls:
        if c['type'] in NO_LABEL_TYPES:
            continue
        named = bool(c['aria']) or c.get('wrapped') or (c['id'] and c['id'] in au.label_for)
        if not named:
            miss.append(c['name'] or c['tag'])
    if miss:
        v.append('无标签控件: ' + ', '.join(sorted(set(miss))[:8]))
    if au.bad_links:
        v.append('%d 个链接无可访问名（如 %s）' % (len(au.bad_links), au.bad_links[0]))
    if au.bad_buttons:
        v.append('%d 个按钮无可访问名' % len(au.bad_buttons))
    dup = [x for x in set(au.ids) if au.ids.count(x) > 1]
    if dup:
        v.append('重复 id: ' + ', '.join(sorted(dup)[:6]))
    # 标题：h1 数量 + 层级跳跃
    hs = au.headings
    if hs:
        if hs.count(1) != 1:
            v.append('h1 数量 = %d（应为 1）' % hs.count(1))
        prev = 0
        for lv in au.headings:
            if prev and lv > prev + 1:
                v.append('标题层级跳跃 h%d → h%d' % (prev, lv))
                break
            prev = lv
    return v


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    strict = '--strict' in sys.argv
    base = args[0].rstrip('/') if args else 'http://127.0.0.1:8081'
    bad = 0
    for p in PAGES:
        try:
            v = check(base, p)
        except Exception as e:
            print('%-14s  取页失败: %s' % (p, e))
            bad += 1
            continue
        if v:
            bad += 1
            print('%-14s  ✗ %s' % (p, '；'.join(v)))
        else:
            print('%-14s  ✓' % p)
    print('\n%d/%d 页有问题' % (bad, len(PAGES)))
    if bad and strict:
        sys.exit(1)


if __name__ == '__main__':
    main()
