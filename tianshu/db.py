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
import time
from contextlib import contextmanager

from config import DATA_DIR


class Store:
    """json 读写：写的时候先落临时文件再改名，断电/崩了也不会写坏原数据

    读带按文件修改时间的缓存：一个页面要读十几份数据，没这层缓存每次请求
    都要来回开十几个文件 —— 这就是之前"每进一个页面都很慢"的主因之一。
    """

    _lock = threading.RLock()          # 多人同时点的时候别互相覆盖
    _cache = {}                        # {路径: (修改时间, 内容)} 文件没变就直接用

    def path(self, key):
        return os.path.join(DATA_DIR, key + '.json')

    def read(self, key, default=None):
        p = self.path(key)
        if not os.path.exists(p):
            self._cache.pop(p, None)
            return default
        try:
            mtime = os.path.getmtime(p)
        except OSError:
            return default
        hit = self._cache.get(p)
        if hit and hit[0] == mtime:
            return hit[1]              # 文件没被外部改过，直接用上一次的内容
        with self._lock:
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:                       # 文件被改坏了也先让站活着
                print('[数据] 读 %s.json 出错：%s' % (key, e))
                return default
            self._cache[p] = (mtime, data)
            return data

    def write(self, key, obj):
        """写盘。Windows 上偶发"拒绝访问"——杀毒软件、OneDrive 同步、别的进程正在读，
          都可能在这一瞬间锁住文件，所以重试几次。

          ⚠️ 重试到底还失败时**必须抛错**（2026-10 修复）：
          以前这里是"直接覆盖目标文件、再失败也只打印日志、最后照样 return obj"，
          业务层于是向用户报告"操作成功"，实际数据根本没落盘 —— 静默丢数据最要命。
          而且直接覆盖目标文件还可能留下半截 JSON，把整张表写坏。
        """
        os.makedirs(DATA_DIR, exist_ok=True)
        p = self.path(key)
        # 临时文件带 pid：多进程/多线程同时写同一张表时不会互相覆盖对方的临时文件
        tmp = '%s.%d.tmp' % (p, os.getpid())
        data = json.dumps(obj, ensure_ascii=False, indent=1)
        with self._lock:
            last_err = None
            for attempt in range(4):
                try:
                    with open(tmp, 'w', encoding='utf-8') as f:
                        f.write(data)
                        f.flush()
                        os.fsync(f.fileno())        # 真的刷到磁盘，别留在系统缓存里
                    os.replace(tmp, p)              # 原子替换：要么全成功，要么原文件不动
                    try:                             # 写完顺手刷新缓存，下次读就不用再开文件
                        self._cache[p] = (os.path.getmtime(p), obj)
                    except OSError:
                        pass
                    return obj
                except (PermissionError, OSError) as e:
                    last_err = e
                    time.sleep(0.08 * (attempt + 1))
            try:                                     # 收尾：别把垃圾临时文件留在 data/ 里
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            raise RuntimeError('写入 %s.json 失败（已重试 4 次）：%s' % (key, last_err))

    def rows(self, key):
        """数组型数据；不存在就给空列表，省得每处都判 None"""
        v = self.read(key)
        return v if isinstance(v, list) else []

    @contextmanager
    def transaction(self):
        """跨多张表的原子区间：整段持锁，别人读不到"扣了款但订单还没建"这种中间状态。

            with db.transaction():
                u['balance'] -= amount        # 改用户
                db.write('users', users)      # 写用户
                db.write('pays', orders)      # 写订单 —— 要么都成，要么都被别的请求看到之前完成
        锁是可重入的（RLock），区间里再调 update()/write() 不会自己把自己锁死。
        """
        with self._lock:
            yield

    def update(self, key, fn, limit=None):
        """读出 → fn 处理 → 写回，整段持锁。

        2026-10 修复：以前是「读（持锁）→ 释放 → fn 处理 → 写（持锁）」，
        两个请求可以同时读到同一份旧数据、各自加 1、再先后写回，结果只加了 1 次（丢更新）。
        现在整段在锁里，读改写不会被并发打断。
        """
        with self._lock:
            rows = self.rows(key)
            out = fn(rows)
            if out is None:
                out = rows
            result = out[:limit] if limit else out
            self.write(key, result)
            return result

    def one(self, key, **cond):
        """按字段找第一条，例：db.one('users', phone='138...')"""
        for row in self.rows(key):
            if all(str(row.get(k)) == str(v) for k, v in cond.items()):
                return row
        return None


db = Store()
