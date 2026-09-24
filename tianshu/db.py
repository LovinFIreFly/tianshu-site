# -*- coding: utf-8 -*-
"""
数据层：整站的数据就是 data/ 下的一堆 json，没有数据库，方便你随时翻出来看

    users.json      账号（含密码哈希、信用分）
    scripts.json    剧本库
    bookings.json   预约（含拼车信息、核销码）
    pays.json       订单（定金/支付/退款）
    sessions.json   场次排期
    coupons.json    优惠券
    notices.json    站内通知
    logs.json       操作日志
    其它：reviews posts messages carmsgs favs wantlist codes settings

用法：
    db.rows('users')                     读一个数组
    db.read('settings')                  读一份配置
    db.write('bookings', rows)           整份写回（改完记得存）
    db.update('notices', lambda r: r[:20])   读-改-写一步到位
"""
import json
import os
import threading

from config import DATA_DIR


class Store:
    """json 读写：写的时候先落临时文件再改名，断电/崩了也不会写坏原数据"""

    _lock = threading.RLock()          # 多人同时点的时候别互相覆盖

    def path(self, key):
        return os.path.join(DATA_DIR, key + '.json')

    def read(self, key, default=None):
        p = self.path(key)
        if not os.path.exists(p):
            return default
        with self._lock:
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:                       # 文件被改坏了也先让站活着
                print('[数据] 读 %s.json 出错：%s' % (key, e))
                return default

    def write(self, key, obj):
        os.makedirs(DATA_DIR, exist_ok=True)
        p, tmp = self.path(key), self.path(key) + '.tmp'
        with self._lock:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(obj, f, ensure_ascii=False, indent=1)
            os.replace(tmp, p)
        return obj

    def rows(self, key):
        """数组型数据；不存在就给空列表，省得每处都判 None"""
        v = self.read(key)
        return v if isinstance(v, list) else []

    def update(self, key, fn, limit=None):
        """读出 → fn 处理 → 写回。fn 直接原地改也行，返回新列表也行"""
        rows = self.rows(key)
        out = fn(rows) or rows
        self.write(key, out[:limit] if limit else out)
        return out

    def one(self, key, **cond):
        """按字段找第一条，例：db.one('users', phone='138...')"""
        for row in self.rows(key):
            if all(str(row.get(k)) == str(v) for k, v in cond.items()):
                return row
        return None


db = Store()
