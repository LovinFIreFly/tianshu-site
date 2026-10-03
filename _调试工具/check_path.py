# -*- coding: utf-8 -*-
import os, pathlib

d = pathlib.Path(r"C:\Users\junbo\Desktop")
print("desktop exists:", d.exists())
for p in d.iterdir():
    if p.is_dir() and ("网" in p.name or "站" in p.name or p.name.startswith("网")):
        print("DIR:", repr(p.name), p)
        for f in p.iterdir():
            print("   FILE:", f.name, f.stat().st_size)
target = pathlib.Path(r"C:\Users\junbo\Desktop\网站\index.html")
print("target:", target, "exists:", target.exists())
print("uri:", target.as_uri())
