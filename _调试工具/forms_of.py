# -*- coding: utf-8 -*-
"""列出某个模板里所有表单的 action 与字段名（用来写自动化测试）"""
import os, re, sys

root = r"C:\Users\junbo\Desktop\网站\tianshu\templates"
target = sys.argv[1]
p = os.path.join(root, target)
with open(p, encoding='utf-8') as f:
    src = f.read()

for m in re.finditer(r'<form[^>]*>(.*?)</form>', src, re.S | re.I):
    head = m.group(0)[:m.group(0).find('>') + 1]
    action = re.search(r'action\s*=\s*"([^"]*)"', head)
    method = re.search(r'method\s*=\s*"([^"]*)"', head)
    names = re.findall(r'<input[^>]*name\s*=\s*"([^"]*)"', m.group(1))
    names += re.findall(r'<select[^>]*name\s*=\s*"([^"]*)"', m.group(1))
    names += re.findall(r'<textarea[^>]*name\s*=\s*"([^"]*)"', m.group(1))
    print('%-6s %-46s %s' % ((method.group(1) if method else 'GET').upper(),
                             (action.group(1) if action else ''), names))
