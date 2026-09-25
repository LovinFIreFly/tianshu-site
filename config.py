# -*- coding: utf-8 -*-
"""
配置：能改的东西都放这儿，别去散落到各个文件里找

    python app.py              启动（默认 8000 端口）
    python app.py --lan        让手机也能访问（同一个 WiFi）
    python app.py --stats      看数据统计
    python app.py --backup     备份 data 到 zip
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')          # 数据、密钥、上传的图都在这
IMG_DIR = os.path.join(DATA_DIR, 'img')

PORT = 8000                    # 被占用会自动往后试 8001、8002…
OPEN_BROWSER = True            # 启动后自动开浏览器
LAN_MODE = False               # 手机访问开关：要测手机端再开（同一 WiFi 下的设备都能进）
SESSION_DAYS = 7               # 登录保持多少天
MAX_IMG_BYTES = 700 * 1024     # 上传图片上限

SECRET_FILE = os.path.join(DATA_DIR, 'secret.key')     # 会话签名密钥，首次运行自动生成

# 经营参数默认值。首次运行会写进 data/settings.json，之后以那个文件为准，
# 网页后台「门店设置」改的就是它 —— 所以想让店里自己调，不用来动代码。
SETTINGS_DEFAULT = {
    "shopName": "甜薯剧本杀",
    "notice": "周末场次紧张，建议提前两天订位",
    "dmFee": 20,               # 指定 DM 的加价（元/人）
    "depositRatio": 0.30,      # 定金比例
    "freeCancelHours": 24,     # 开场前 N 小时内取消算临期
    "lateCancelPenalty": 2,    # 临期取消扣的信用分
    "dmRate": 0.10,            # DM 分成比例（dmPayMode = 'rate' 时生效）
    "dmPayMode": "rate",       # DM 怎么拿钱：rate=按营业额分成 / fixed=每场固定场费
    "dmFixedPay": 150,         # dmPayMode = 'fixed' 时，每场给多少
    "reviewsEnabled": True,    # 是否展示评分
    "carTags": ["不跳车", "准时到场", "新手友好", "硬核玩家"],
}

# 内置账号（用户名 / 手机号 / 角色 / 超管），密码统一 123123
SEED_USERS = [
    ('FireFly', '13552158081', 'super', True),
    ('FireFly2', '18732303179', 'admin', False),
    ('dm测试', '12345678901', 'dm', False),
    ('调试debug', '13800000000', 'user', False),
]

WEEK = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

# 默认房间（首次运行写进 data/rooms.json，之后在后台「排期」页里加/删）
ROOMS_DEFAULT = [
    {'id': 1, 'name': 'A房', 'cap': 6, 'dev': '投影 + 音响'},
    {'id': 2, 'name': 'B房', 'cap': 8, 'dev': '投影 + 音响 + 换装间'},
    {'id': 3, 'name': '大房', 'cap': 10, 'dev': '环绕音响 + 灯光舞台'},
]
