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
          都可能在这一瞬间锁住文件。所以重试几次，实在不行就直接写目标文件（少一点原子性，别让功能挂掉）。
          （这个坑是跑自检时踩出来的：接口直接 500）"""
        os.makedirs(DATA_DIR, exist_ok=True)
        p, tmp = self.path(key), self.path(key) + '.tmp'
        data = json.dumps(obj, ensure_ascii=False, indent=1)
        with self._lock:
            for attempt in range(4):
                try:
                    with open(tmp, 'w', encoding='utf-8') as f:
                        f.write(data)
                    os.replace(tmp, p)
                    try:                             # 写完顺手刷新缓存，下次读就不用再开文件
                        self._cache[p] = (os.path.getmtime(p), obj)
                    except OSError:
                        pass
                    return obj
                except PermissionError:
                    time.sleep(0.08 * (attempt + 1))
                except OSError as e:
                    if attempt == 3:
                        print('[数据] 写 %s.json 出错：%s' % (key, e))
                        break
            try:
                with open(p, 'w', encoding='utf-8') as f:
                    f.write(data)
            except Exception as e:
                print('[数据] %s.json 兜底写入也失败了：%s' % (key, e))
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
