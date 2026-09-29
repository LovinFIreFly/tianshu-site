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
# 数据、密钥、上传的图都在这。默认就是项目里的 data/；
# 想跑在别的地方（自检就是这么干的：临时目录、跑完就删、不弄脏真实数据），
# 设环境变量 TS_DATA_DIR 指过去即可 —— 必须在启动**之前**设好。
DATA_DIR = os.path.abspath(os.environ.get('TS_DATA_DIR') or os.path.join(BASE_DIR, 'data'))
IMG_DIR = os.path.join(DATA_DIR, 'img')

PORT = 8000                    # 被占用会自动往后试 8001、8002…
OPEN_BROWSER = True            # 启动后自动开浏览器
LAN_MODE = False               # 手机访问开关：要测手机端再开（同一 WiFi 下的设备都能进）
SESSION_DAYS = 180             # 登录保持多少天（半年）—— 客人最烦的就是"又要登一次"，
                           # 尤其注册得收邮箱验证码。共享设备/员工机在登录页把「记住我」取消勾选就行
SESSION_TIMES = ['13:00', '15:30', '19:00', '20:30', '21:30']   # 排期可选的开场时间（店里就这几档）
TAG_PRESETS = [                # 剧本标签（参考主流剧本杀平台的分类，客人筛、后台点）
    '情感', '沉浸', '推理', '硬核', '还原', '欢乐', '恐怖', '微恐', '机制', '阵营',
    '古风', '民国', '现代', '未来', '童话', '新手友好', '进阶烧脑', '神反转', '独家', '城限',
]
MAX_IMG_BYTES = 700 * 1024     # 上传图片上限
TEMPLATES_AUTO_RELOAD = False  # 页面速度优化：平时关掉（改模板后重启生效）；开发时用 python app.py --dev

# 通用验证码：本地没接短信服务商，靠它让改密码/换绑/注销这些流程能走通。
# 真要放线上对外服务，这里必须换成真发短信（删掉这行也不影响程序，只是验证码只能靠窗口里那个）
DEMO_CODE = '1234'

SECRET_FILE = os.path.join(DATA_DIR, 'secret.key')     # 会话签名密钥，首次运行自动生成

# 经营参数默认值。首次运行会写进 data/settings.json，之后以那个文件为准，
# 网页后台「门店设置」改的就是它 —— 所以想让店里自己调，不用来动代码。
SETTINGS_DEFAULT = {
    "shopName": "甜薯剧本杀",
    "notice": "周末场次紧张，建议提前两天订位",
    "dmFee": 20,               # 指定 DM 的加价（元/人）
    "depositRatio": 0.30,      # 定金比例（包车用这个算）
    "carDeposit": 50,          # 拼车定金：一口价（元），跟人数无关
    "inviteCoupon": 10,        # 邀请返利：填了邀请码注册，双方各得一张券（元）
    # ---- 验证码发信 ----
    # 三条通道任选一条（后台「门店设置 → 验证码发信」里选）；留空 = 不真发，
    # 验证码只打印在跑服务的黑窗口里（本机开发够用；线上必须配一条，不然客人收不到码）
    #   ① resend  —— 和老版（legacy/functions/api）用的同一个服务，免费 3000 封/月
    #   ② smtp    —— 阿里云邮件推送 / QQ 邮箱等，直连 SMTP
    #   ③ webhook —— 往你自己的接口 POST，爱接啥接啥
    "mailProvider": "",        # '' / 'resend' / 'smtp' / 'webhook'
    "mailKey": "",             # Resend API Key（re_ 开头）
    "mailFrom": "",            # 发件人，例：noreply@lovinfirefly.cn（Resend 里验证过的域名）
    "mailFromName": "甜薯剧本杀",   # 发件人昵称（收件箱里显示的名字）；留空 = 只显示邮箱地址
    # 站点外观款式：**手机端 / 电脑端分开选**（后台「门店设置 → 外观款式」里各挑一个）
    # 可选值见 business.SKINS；二选一留空就回退到下面的 skin（历史部署兼容用）
    "skin_desktop": "playbill",
    "skin_mobile": "playbill",
    # 手机端方案：app=独立手机站(/m，与桌面站完全分开)；legacy=沿用旧原生层(skin_mobile)
    "mobileMode": "app",
    # 历史兼容：单款式旧值，二选一都没配时回退到这里
    "skin": "playbill",
    # 店铺实拍（"真实照片前置"用）：后台「门店设置」里传，首页会挂一条照片墙
    "shopPhotos": [],          # 形如 [{'url':'/img/shop/...','cap':'前台'}, ...]
    "shopIntro": "",           # 店铺一句话（实拍区旁边配的手写小字）
    "mailSubject": "",         # 主题，留空 = 【店名】验证码
    "mailWebhook": "",         # 自定义 Webhook 地址
    "smtpHost": "",            # 例：smtpdm.aliyun.com
    "smtpPort": 465,           # 465 = SSL（推荐）；587 = STARTTLS。别用 25，云厂商默认封
    "smtpUser": "",            # 发信账号，例：noreply@lovinfirefly.cn
    "smtpPass": "",            # SMTP 密码（在邮件推送控制台单独设置，不是登录密码）
    "smtpFrom": "",            # 发件人地址，留空就用 smtpUser
    "serviceWechat": "tianshu-kefu",   # 小客服微信号（客人付定金那页显示，记得改成真的）
    "freeCancelHours": 24,     # 开场前 N 小时内取消算临期
    "lateCancelPenalty": 2,    # 临期取消扣的信用分
    "dmRate": 0.10,            # DM 分成比例（dmPayMode = 'rate' 时生效）
    "dmPayMode": "rate",       # DM 怎么拿钱：rate=按营业额分成 / fixed=每场固定场费
    "dmFixedPay": 150,         # dmPayMode = 'fixed' 时，每场给多少
    "reviewsEnabled": True,    # 是否展示评分
    "carTags": ["不跳车", "准时到场", "新手友好", "硬核玩家"],
    # 首页轮播（后台「门店设置」里可以改，一行一条：表情|标题|一句话|剧本id（0=不跳））
    "banners": [
        {'emoji': '🎭', 'title': '沉浸式开本 · 专业 DM', 'text': '一场好戏，从甜薯开始', 'sid': 0},
        {'emoji': '🚗', 'title': '一个人也能玩', 'text': '去拼车大厅看看，凑齐就开局', 'sid': 0},
        {'emoji': '🎁', 'title': '邀友各得 ¥10 券', 'text': '注册时填好友的邀请码，你俩各得一张抵扣券', 'sid': 0},
    ],
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
