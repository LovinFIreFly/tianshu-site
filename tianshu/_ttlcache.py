# -*- coding: utf-8 -*-
"""轻量进程内 TTL 缓存（升级包引入，business.py 的 get_or_set 依赖它）。

只有一个接口：
    get_or_set(key, ttl, producer)
      - key      可哈希（str 或 tuple 都行）
      - ttl      秒；<=0 表示不缓存（每次都重算）
      - producer 无参可调用，返回要缓存的值

命中且未过期就直接返回缓存；否则调 producer 算一份存起来再返回。
用一把锁挡住多 worker 并发（waitress 16 线程），避免同一时刻重复算 + 竞态写。
"""
import threading
import time

_cache = {}
_lock = threading.Lock()


def get_or_set(key, ttl, producer):
    if ttl and ttl > 0:
        with _lock:
            if key in _cache:
                ts, val = _cache[key]
                if (time.time() - ts) < ttl:
                    return val
    val = producer()
    if ttl and ttl > 0:
        with _lock:
            _cache[key] = (time.time(), val)
    return val


def invalidate(*keys):
    """写操作后手动作废缓存 —— 不调它的话，页面最长会回显一整个 TTL 的旧数据。

    真实踩坑：上车成功后 car_pool 还端着 15 秒前的旧成员表，详情页成员数不变、
    「我要上车」按钮还杵在那，客人以为点了没用（2026-10 用户反馈）。"""
    with _lock:
        for k in keys:
            _cache.pop(k, None)
