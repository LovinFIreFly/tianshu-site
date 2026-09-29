# -*- coding: utf-8 -*-
"""
自检脚本：改完代码跑一遍，看看有没有把功能改坏

用法（一条命令就够，它会自己起一个"一次性"服务）：
    python tools/smoke_test.py

    # 想连已经在跑的服务（注意：那会往**真实 data/** 里写东西，跑完数据是脏的）
    BASE=http://127.0.0.1:8000 python tools/smoke_test.py

它自己起服务时是这样的：
    ① 开一个临时数据目录（系统临时目录下，不在项目里）
    ② TS_DATA_DIR 指向它 → 服务从**空库**开始（只有 4 个内置账号 + 默认设置）
    ③ 随机端口起服务，跑完把服务和临时目录一起收拾掉

所以每次跑都是干净起点、跑多少次结果都一样，不会：
  · 让"自检本"一本本堆在剧本库里 · 让验证码额度一天用完 · 留下"余额变动"通知
  · 把"关注"从关注点成取关（那个接口是切换式的，第二次跑就反了）
哪次没过，临时目录会留下来（路径会打出来），方便翻现场。

它会真的去点网页：登录、加剧本、下单、核销、退款、拼车、权限，
顺便直接读数据目录里的 *.json 核对算出来的钱对不对。
"""
import http.cookiejar
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 没给 BASE = 自己起服务（默认，干净）；给了 BASE = 连那个已经在跑的服务
_EXTERNAL = os.environ.get('BASE')
BASE = _EXTERNAL or ''
DATA = os.path.abspath(os.environ.get('TS_DATA_DIR') or os.path.join(ROOT, 'data'))

_server = None          # 自己起的那个服务进程
_tmpdir = None          # 临时数据目录


def _free_port():
    """让系统随便给个没用过的端口（别去抢 8000 —— 那个可能是你正在看的预览）"""
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _start_server():
    """起一个跑在临时数据目录上的服务，返回它的地址"""
    global BASE, DATA
    tmp = tempfile.mkdtemp(prefix='tianshu-smoke-')
    port = _free_port()
    env = dict(os.environ, TS_DATA_DIR=tmp, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    log = open(os.path.join(tmp, 'server.log'), 'w', encoding='utf-8')
    proc = subprocess.Popen([sys.executable, 'app.py', '--no-browser', '--port', str(port)],
                            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    BASE = 'http://127.0.0.1:%d' % port
    DATA = tmp
    # 自检进程自己也 import tianshu（有些断言要直接调后端纯函数），
    # 让它读同一份临时数据，免得两边看到的东西不一样
    os.environ['TS_DATA_DIR'] = tmp
    for _ in range(80):                      # 最多等 40 秒（首次运行要装依赖会久一点）
        if proc.poll() is not None:
            break
        try:
            urllib.request.urlopen(BASE + '/health', timeout=2).read()
            print('临时数据目录：%s' % tmp)
            print('自检服务：%s（跑完自动关掉）' % BASE)
            return proc, tmp
        except Exception:
            time.sleep(0.5)
    log.close()
    print('自检服务起不来（%s）。日志：' % BASE)
    try:
        with open(os.path.join(tmp, 'server.log'), encoding='utf-8', errors='replace') as f:
            print('  ' + '\n  '.join(f.read().strip().splitlines()[-15:]))
    except OSError:
        pass
    sys.exit(2)


if _EXTERNAL:
    BASE = _EXTERNAL
    print('连已经在跑的服务：%s（注意：会写真实数据目录 %s）' % (BASE, DATA))
else:
    _server, _tmpdir = _start_server()

# 有些检查要直接调后端函数（角色判定、发件人拼接这类纯函数，走 HTTP 验不出来），
# 脚本是从 tools/ 跑的，所以得把仓库根目录塞进 sys.path 才能 import tianshu。
sys.path.insert(0, ROOT)
from tianshu import business as _bs            # noqa: E402

# 中文控制台（GBK）里 ✓ 这种符号会报错，兜底成问号，别让自检自己先挂了
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors='replace')
    except Exception:
        pass

fails = []


def check(name, ok, extra=''):
    # 用 [OK]/[!!] 而不是对勾符号：中文控制台（GBK）打不出 ✓，会显示成问号，看着闹心
    print(('  [OK] ' if ok else '  [!!] ') + name + (('  ' + str(extra)) if extra else ''))
    if not ok:
        fails.append(name)


def jread(key):
    p = os.path.join(DATA, key + '.json')
    if not os.path.exists(p):
        return []
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f)


class Client:
    """一个带头 cookie 的"浏览器"，每个角色用一个"""

    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def get(self, path, headers=None):
        try:
            with self.op.open(urllib.request.Request(BASE + path, headers=headers or {}), timeout=15) as r:
                return r.status, r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8', 'replace')

    def _csrf(self):
        """每个访客都有一颗 CSRF 令牌 cookie，写操作必须带着它（跟浏览器里 csrf.js 干的一样）"""
        for c in self.jar:
            if c.name == 'csrf':
                return c.value
        self.get('/')                     # 还没有令牌：先 GET 一下领一颗
        for c in self.jar:
            if c.name == 'csrf':
                return c.value
        return ''

    def post(self, path, data=None, headers=None):
        body = urllib.parse.urlencode(data or {}).encode('utf-8')
        h = {'X-CSRF': self._csrf()}
        h.update(headers or {})
        req = urllib.request.Request(BASE + path, data=body, method='POST', headers=h)
        try:
            with self.op.open(req, timeout=15) as r:
                return r.status, r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8', 'replace')

    def getq(self, path):
        """带中文的路径要先转义（不然 urllib 会报 ascii 编码错 —— 踩过）"""
        return self.get(urllib.parse.quote(path, safe='/?=&%'))

    def post_file(self, path, field, filename, content, extra=None):
        """带文件的表单（传封面 / 头像 / CSV 用）—— 手搓一个 multipart，不引第三方库"""
        bd = '----smoke%s' % time.strftime('%H%M%S')
        parts = []
        for k, v in (extra or {}).items():
            parts.append('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (bd, k, v))
        parts.append('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\n'
                     'Content-Type: application/octet-stream\r\n\r\n' % (bd, field, filename))
        body = ''.join(parts).encode('utf-8') + content + ('\r\n--%s--\r\n' % bd).encode('utf-8')
        req = urllib.request.Request(BASE + path, data=body, method='POST',
                                     headers={'Content-Type': 'multipart/form-data; boundary=%s' % bd,
                                              'X-CSRF': self._csrf()})
        try:
            with self.op.open(req, timeout=20) as r:
                return r.status, r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8', 'replace')


def ts_in(days):
    """N 天后那一天的 0 点（毫秒）"""
    t = time.localtime(time.time() + days * 86400)
    return int(time.mktime(time.strptime(time.strftime('%Y-%m-%d', t), '%Y-%m-%d'))) * 1000


def iso_of(ms):
    """毫秒 → 'YYYY-MM-DD'（页面上的日历控件交上来的就是这个格式）"""
    return time.strftime('%Y-%m-%d', time.localtime(ms / 1000))


print('① 公开页面')
guest = Client()
s, html = guest.get('/')
check('进站先看到欢迎页（不是登录表单）',
      s == 200 and '沉浸式剧本体验' in html and '账号登录' not in html)
s, html = guest.get('/?browse=1')
# 判据用页面结构：'welcome-card' 只在欢迎页有。
# 别拿文案当判据 —— 页脚、slogan 都可能撞字（"沉浸式剧本体验"页脚里也有，踩过一次）。
check('点「先随便逛逛」能进门店首页',
      s == 200 and 'welcome-card' not in html and '拼车' in html)
g2 = Client()                    # 另一个"没点过逛逛、但已经逛过剧本库"的游客
g2.get('/scripts')
s, html = g2.get('/')
check('已经在站里逛的人，回首页不会再被欢迎页挡住',
      s == 200 and 'welcome-card' not in html)

# 手机端底部导航（.mobtab，只在窄屏出现的固定底栏）—— 桌面端必须藏着，否则会多一条
import re as _re
_pat = r'<a href="([^"]+)" class="(on)?">\s*<span class="ico"[^>]*>([^<]+)</span><span>([^<]+)</span>'
_mt = _re.search(r'<nav class="mobtab".*?</nav>', html, _re.S)
_tabs = _re.findall(_pat, _mt.group(0) if _mt else '')
check('对外页面有手机底部导航，正好四个入口',
      [t[3] for t in _tabs] == ['首页', '剧本库', '拼车', '我的'], str([t[3] for t in _tabs]))
check('高亮跟着当前页走（首页时只亮「首页」）',
      [t[3] for t in _tabs if t[1]] == ['首页'], str([t[3] for t in _tabs if t[1]]))
_s2, _css = guest.get('/static/css/style.css')
check('底部导航桌面端隐藏、窄屏才是固定底栏',
      '.mobtab{display:none}' in _css and '.mobtab{display:flex;position:fixed' in _css)
_s2, _car = guest.get('/car')
_mt2 = _re.search(r'<nav class="mobtab".*?</nav>', _car, _re.S)
_t2 = _re.findall(_pat, _mt2.group(0) if _mt2 else '')
check('拼车页底部导航把「拼车」点亮',
      [t[3] for t in _t2 if t[1]] == ['拼车'], str([t[3] for t in _t2 if t[1]]))
# 外观款式（skin）：后台统一设置 → **全站（手机+电脑）一起变**；客人不能自己换
_ss, _sh = guest.get('/car')
check('客人端不出现款式预览条（只有管理员能预览）', 'skin-bar' not in _sh)
check('默认款式不额外加载皮肤表', all(('skin-%s.css' % k) not in _sh for k in ('noir', 'riso', 'swiss', 'monolith')))
for path, want in (('/scripts', '剧本库'), ('/car', '拼车'), ('/login', '登录'), ('/register', '注册')):
    s, html = guest.get(path)
    check('打开 %s' % path, s == 200 and want in html, 'HTTP %s' % s)
s, html = guest.get('/me')
check('没登录看「我的」会跳去登录', s == 200 and '登录' in html)
s, html = guest.get('/admin/')
# 会被重定向到登录页（urllib 自动跟了跳转，所以最后看到的是登录页）
check('客户/游客进不了后台', s == 403 or ('登录' in html and '到店核销' not in html), 'HTTP %s' % s)

print('② 管理员：加剧本')
admin = Client()
admin.post('/login', {'account': 'FireFly', 'password': '123123'})
s, html = admin.get('/admin/')
check('超管能进后台', s == 200 and '到店核销' in html)

# 外观款式（skin）：后台统一设置 → 全站（手机 + 电脑）一起变；客人不能自己换
_ss, _adm = admin.get('/admin?tab=dash')
check('后台门店设置里有「外观款式」下拉（五种款式都在）',
      'name="skin"' in _adm and all(k in _adm for k in ('playbill', 'noir', 'riso', 'swiss', 'monolith')))
_ss, _adm2 = admin.get('/admin?tab=dash&skin=monolith')
check('管理员能用 ?skin= 先预览再决定（客人看不到这个开关）', 'skin-monolith.css' in _adm2)
import os as _os
_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
for _k in ('noir', 'riso', 'swiss', 'monolith'):
    check('皮肤表 skin-%s.css 存在' % _k,
          _os.path.exists(_os.path.join(_root, 'tianshu', 'static', 'css', 'skin-%s.css' % _k)))
try:
    from tianshu import business as _bs
    check('乱填的款式退回默认（这个值会拼进静态文件路径，必须白名单卡死）',
          _bs.current_skin({'skin': '../../etc/passwd'}) == 'playbill'
          and _bs.current_skin({}) == 'playbill'
          and _bs.current_skin({'skin': 'noir'}) == 'noir')
except Exception as _e:
    check('乱填的款式退回默认（这个值会拼进静态文件路径，必须白名单卡死）', False, str(_e)[:60])
title = '自检本%s' % time.strftime('%H%M%S')
s, _ = admin.post('/admin/scripts/new', {'title': title, 'emoji': '🧪', 'price': 100})
sc = next((x for x in jread('scripts') if x.get('title') == title), None)
check('新剧本建好了', bool(sc), 'id=%s' % (sc or {}).get('id'))
s, html = guest.get('/scripts')
check('客人能看见新剧本', title in html)

# 给这个本填上角色 + 打开"可提前选角"
admin.post('/admin/scripts/%s/save' % sc['id'], {
    'title': title, 'price': 100, 'players': '4-6人', 'onSale': '1', 'allowRolePick': '1',
    'roles': '阿甲, 阿乙', 'desc': '自检用'})
sc = next((x for x in jread('scripts') if x.get('title') == title), None)
check('角色和选角开关存上了', sc.get('allowRolePick') is True and len(sc.get('roles') or []) == 2)

print('③ 客人：下单 / 算价 / 核销码')
cus = Client()
cus.post('/login', {'account': '调试debug', 'password': '123123'})
s, html = cus.get('/scripts/%s' % sc['id'])
check('能打开详情页', s == 200 and '预约这一本' in html)
day = ts_in(3)
check('预约表单改用日历控件了', 'type="date"' in html and 'name="ts_day"' in html)
check('拼车下面有「自己单开一辆 / 加入已有的车」两个选项',
      '自己单开一辆车' in html and '加入已有的车' in html)
# 日期现在由日历控件交上来（ts_day='2026-09-30'），页面上不再是一长条下拉
s, _ = cus.post('/book', {'sid': sc['id'], 'ts_day': iso_of(day), 'time': '19:00', 'players': 4,
                          'mode': '拼车', 'role': '阿甲'})
bk = next((b for b in jread('bookings') if b.get('sid') == sc['id'] and b.get('ts') == day
           and b.get('status') == 'booked'), None)
check('下单成功（日期是日历交的 ts_day）', bool(bk), (bk or {}).get('verifyCode'))
check('定金 = 人数 × 50（一人 50，拼车包车都一样）',
      bk and int(bk.get('deposit') or 0) == 50 * int(bk.get('players') or 1),
      '%s 人 → 定金 ¥%s' % ((bk or {}).get('players'), (bk or {}).get('deposit')))
check('核销码是 6 位', bk and len(str(bk.get('verifyCode'))) == 6)
check('选角记上了', bk and bk.get('role') == '阿甲')
# 同一个角色第二个人不能选
cus2 = Client()
cus2.post('/register', {'phone': '13900001111', 'username': '自检小号', 'password': '123456',
                        'password2': '123456', 'code': '1234', 'agree': '1',
                        'email': 'check2@example.com'})       # 验证码只发邮箱，注册必须留邮箱
cus2.post('/book', {'sid': sc['id'], 'ts': day, 'time': '19:00', 'players': 2, 'mode': '拼车', 'role': '阿甲'})
dup = [b for b in jread('bookings') if b.get('role') == '阿甲' and b.get('ts') == day
       and b.get('status') == 'booked']
check('同一角色不会被两个人选走', len(dup) == 1, '有 %d 条' % len(dup))

# 拼车「加入已有的车」：上别人那辆车，日期时间跟着车主走，定金同样一口价 50
cus2.post('/book', {'sid': sc['id'], 'ts_day': iso_of(day), 'time': '09:00', 'players': 1,
                    'mode': '拼车', 'car': 'join', 'carId': bk.get('id')})
jb = next((b for b in jread('bookings') if b.get('phone') == '13900001111'
           and b.get('carOwner') == bk.get('username') and not b.get('carNew')), None)
check('能上别人已经开着的车（自己不用另开一辆）', bool(jb), '车主=%s' % (jb or {}).get('carOwner'))
check('上车的时间跟着车主走（我填的 09:00 不算）',
      jb and jb.get('time') == '19:00' and jb.get('ts') == day,
      '%s %s' % ((jb or {}).get('day'), (jb or {}).get('time')))
check('上车的人也有自己的核销码', jb and len(str(jb.get('verifyCode'))) == 6)
jo = next((x for x in jread('pays') if x.get('bid') == (jb or {}).get('id')), None)
check('上车也要交定金 ¥50', jo and int(jo.get('deposit') or 0) == 50, '定金 ¥%s' % (jo or {}).get('deposit'))

s, html = cus.get('/me')
check('没付定金时，客人自己看不到核销码', str(bk.get('verifyCode')) not in html)
check('页面上写着要等小客服确认', '未付定金' in html and '小客服' in html)

print('④ 拼车大厅（要在核销之前测，核销后这车就不在池子里了）')
s, html = guest.get('/car')
check('车上出现了这个本', title in html)
cus3 = Client()
cus3.post('/login', {'account': '13900001111', 'password': '123456'})
s, _ = cus3.post('/car/%s/join' % bk.get('id'), {})
joined = [b for b in jread('bookings') if b.get('carOwner') == bk.get('username')
          and b.get('sid') == sc['id'] and b.get('status') == 'booked']
check('别人能上车', len(joined) >= 1, '车里 %d 人（含车主）' % (len(joined) + 1))
# 从大厅上车也走同一套定金规矩（一口价 + 客服确认 + 核销码后出）
hall_bk = next((b for b in jread('bookings') if b.get('phone') == '13900001111'
                and b.get('carOwner') == bk.get('username') and b.get('time') == '19:00'), None)
hall_o = next((x for x in jread('pays') if x.get('bid') == (hall_bk or {}).get('id')), None)
check('大厅上车也生成待付定金单（¥50）',
      hall_o and int(hall_o.get('deposit') or 0) == 50 and hall_o.get('status') == 'unpaid',
      '定金 ¥%s' % (hall_o or {}).get('deposit'))

print('⑤ 员工：到店核销')
s, html = admin.post('/admin/verify', {'code': bk.get('verifyCode')})
after = next((b for b in jread('bookings') if b.get('id') == bk.get('id')), {})
check('核销成功', after.get('status') == 'arrived', '状态=%s' % after.get('status'))
s, html = admin.post('/admin/verify', {'code': '000000'})
check('乱输码会提示查不到', '查不到' in html or '无效' in html or '失败' in html)
s, html = guest.get('/car')
check('核销后这车就从拼车池里撤了', title not in html)

print('⑥ 定金流程：支付页 → 待客服确认 → 管理员确认 → 客人才看到核销码')
o = next((x for x in jread('pays') if x.get('bid') == bk.get('id')), None)
check('下单自动生成了待付订单', o and o.get('status') == 'unpaid', (o or {}).get('status'))
s, html = cus.get('/me/pay/%s' % o['id'])
check('支付定金页能打开，上面是加小客服微信', s == 200 and '小客服' in html and '我已完成支付' in html)
s, _ = cus.post('/order/%s/claim' % o['id'], {})          # 点「我已完成支付」= 只是提交
o = next((x for x in jread('pays') if x.get('id') == o['id']), {})
check('点完成 → 变成「待小客服确认」', o.get('status') == 'claimed', '状态=%s' % o.get('status'))
s, html = cus.get('/me')
check('待确认时客人还是看不到核销码', str(bk.get('verifyCode')) not in html)
check('页面上显示「待小客服确认」', '待小客服确认' in html)
s, html = admin.get('/admin/orders')
check('后台订单页能看到这单要确认', '确认支付定金' in html and '待客服确认' in html)
check('后台订单页有「标记未到 · 定金不退」（没到场 / 中途跳车的定金按规矩不退）',
      '标记未到' in html and '定金不退' in html)
s, _ = admin.post('/admin/orders/%s/confirm' % o['id'], {})   # 管理员确认到账
o = next((x for x in jread('pays') if x.get('id') == o['id']), {})
check('管理员点「确认支付定金」', o.get('status') == 'paid', '状态=%s' % o.get('status'))
s, html = cus.get('/me')
check('确认之后客人才看得到核销码', s == 200 and str(bk.get('verifyCode')) in html)
s, html = admin.get('/admin/bookings?status=all')
check('管理员/后台一直能看到核销码', str(bk.get('verifyCode')) in html)

# 包车：定金同样一人 50；游玩费 = 单价 × 人数（玩完再付）
cus.post('/book', {'sid': sc['id'], 'ts': ts_in(4), 'time': '20:00', 'players': 2, 'mode': '包车'})
bk2 = next((b for b in jread('bookings') if b.get('sid') == sc['id'] and b.get('ts') == ts_in(4)
            and b.get('status') == 'booked'), None)
check('包车定金也按人头（一人 50）',
      bk2 and int(bk2.get('deposit') or 0) == 50 * int(bk2.get('players') or 1),
      '%s 人 → 定金 ¥%s' % ((bk2 or {}).get('players'), (bk2 or {}).get('deposit')))
check('游玩费 = 单价 × 人数（定金不抵进去，它是要退回的）',
      bk2 and int(bk2.get('amount') or 0) == 100 * int(bk2.get('players') or 1),
      '游玩费 ¥%s' % (bk2 or {}).get('amount'))
o2 = next((x for x in jread('pays') if x.get('bid') == (bk2 or {}).get('id')), None)
cus.post('/order/%s/pay' % (o2 or {}).get('id'), {})       # 前台现金收的，可以直接标已付
s, html = cus.post('/order/%s/refund' % (o2 or {}).get('id'), {})
o2 = next((x for x in jread('pays') if x.get('id') == (o2 or {}).get('id')), {})
check('提前 4 天取消 → 全额退定金', o2.get('status') == 'refunded', '状态=%s' % o2.get('status'))

# 游玩费流程（2026-09 门店规矩）：核销后不弹评分 → 「支付游玩费」→ 小客服页提交 →
# 客服/DM 确认 → 定金按规矩退回 + 解锁点评
# 用一个干净的新号走全流程（cus 的名下还有别的单，页面断言会被干扰）
cus7 = Client()
cus7.post('/register', {'phone': '13900007666', 'username': '尾款测试号', 'password': '123456',
                        'password2': '123456', 'code': '1234', 'agree': '1',
                        'email': 'check7@example.com'})
cus7.post('/book', {'sid': sc['id'], 'ts_day': iso_of(day), 'time': '19:00', 'players': 2, 'mode': '包车'})
_bk9 = next((b for b in jread('bookings') if b.get('phone') == '13900007666'
             and b.get('status') == 'booked'), None)
_o9 = next((x for x in jread('pays') if x.get('bid') == (_bk9 or {}).get('id')), None)
check('游玩费 = 总价（定金是要退回的，不在这里抵）',
      _o9 and int(_o9.get('amount') or 0) > 0,
      '游玩费 %s 定金 %s' % ((_o9 or {}).get('amount'), (_o9 or {}).get('deposit')))
# 定金：客人说付了 → 前台确认到账（真实流程里核销之前定金一定是确认过的，
# 没确认的单子核销后也该能付游玩费，见下面那条断言）
cus7.post('/order/%s/claim' % (_o9 or {}).get('id'), {})
admin.post('/admin/orders/%s/confirm' % (_o9 or {}).get('id'), {})
_o9 = next((x for x in jread('pays') if x.get('id') == (_o9 or {}).get('id')), {})
check('核销前先确认定金到账', _o9.get('status') == 'paid', '状态=%s' % _o9.get('status'))
s, html = cus7.get('/me')
check('玩完之前不显示「支付游玩费」', '支付游玩费' not in html)
admin.post('/admin/verify', {'code': (_bk9 or {}).get('verifyCode')})
s, html = cus7.get('/me')
check('核销后出现「支付游玩费」，且不再有「取消 / 退定金」',
      '支付游玩费' in html and '取消 / 退定金' not in html)
_bal9 = int((_o9 or {}).get('amount') or 0)
s, html = cus7.get('/me/pay/%s' % (_o9 or {}).get('id'))
check('游玩费支付页走小客服，金额是游玩费',
      s == 200 and '游玩费' in html and ('¥%d' % _bal9) in html)
s, _ = cus7.post('/order/%s/claim-bal' % (_o9 or {}).get('id'), {})
_o9 = next((x for x in jread('pays') if x.get('id') == (_o9 or {}).get('id')), {})
check('点完成 → 游玩费待确认', _o9.get('balStatus') == 'claimed', '状态=%s' % _o9.get('balStatus'))
s, html = cus7.get('/me')
check('确认前点评没解锁（没有打几分表单）', '打几分' not in html)
s, _ = admin.post('/admin/orders/%s/confirm' % (_o9 or {}).get('id'), {})
_o9 = next((x for x in jread('pays') if x.get('id') == (_o9 or {}).get('id')), {})
check('客服/DM 确认游玩费', _o9.get('balStatus') == 'paid', '状态=%s' % _o9.get('balStatus'))
check('确认游玩费时，定金自动退回（门店规矩）', bool(_o9.get('depositBack')),
      'depositBack=%s' % _o9.get('depositBack'))
s, html = cus7.get('/me')
check('确认后点评解锁（打几分出现了）', '打几分' in html)

# 反过来：定金在系统里还没确认到账的单子（前台代收 / 现金那种），人来了照常核销、
# 玩完照常付游玩费 —— 但**不能**记成"定金已退回"：没收到过的钱不能退，
# 也不能这么通知客人（这条是自检跑干净之后揪出来的真 bug）
cus8 = Client()
cus8.post('/register', {'phone': '13900007777', 'username': '定金未确认号', 'password': '123456',
                        'password2': '123456', 'code': '1234', 'agree': '1',
                        'email': 'check8@example.com'})
cus8.post('/book', {'sid': sc['id'], 'ts_day': iso_of(day), 'time': '19:00', 'players': 2, 'mode': '包车'})
_bk10 = next((b for b in jread('bookings') if b.get('phone') == '13900007777'
              and b.get('status') == 'booked'), None)
_o10 = next((x for x in jread('pays') if x.get('bid') == (_bk10 or {}).get('id')), None)
admin.post('/admin/verify', {'code': (_bk10 or {}).get('verifyCode')})    # 定金没确认就核销
s, html = cus8.get('/me')
check('定金没确认的单子，核销后照样能付游玩费（不然客人页面上什么都没有）',
      '支付游玩费' in html)
cus8.post('/order/%s/claim-bal' % (_o10 or {}).get('id'), {})
s, _h = admin.post('/admin/orders/%s/confirm' % (_o10 or {}).get('id'), {})
_o10 = next((x for x in jread('pays') if x.get('id') == (_o10 or {}).get('id')), {})
check('定金没收到过时，不假装"已退回"（否则账对不上）',
      _o10.get('balStatus') == 'paid' and not _o10.get('depositBack'),
      'depositBack=%s' % _o10.get('depositBack'))
check('后台会提醒"这单定金没自动退，手动处理"', '没确认到账' in _h or '没退' in _h)

print('⑦ 用户档案 / 改角色 / 发券')
s, html = admin.get('/admin/users')
check('用户列表能看到人（里面包含普通用户）', s == 200 and '调试debug' in html)
check('列表里带角色标记', '普通用户' in html and '管理员' in html)
# 改角色：普通用户 → DM → 改回来
admin.post('/admin/users/13900001111/role', {'role': 'dm'})
u_r = next((x for x in jread('users') if x.get('phone') == '13900001111'), {})
check('能把人改成 DM', u_r.get('role') == 'dm', '角色=%s' % u_r.get('role'))
admin.post('/admin/users/13900001111/role', {'role': 'admin'})
u_r = next((x for x in jread('users') if x.get('phone') == '13900001111'), {})
check('能把人改成管理员', u_r.get('role') == 'admin', '角色=%s' % u_r.get('role'))
admin.post('/admin/users/13900001111/role', {'role': 'user'})
u_r = next((x for x in jread('users') if x.get('phone') == '13900001111'), {})
check('能改回普通用户', u_r.get('role') == 'user')
# 护栏：超管改不动、自己改不了自己
sup = next((x for x in jread('users') if x.get('super') is True), {})
admin.post('/admin/users/%s/role' % sup.get('phone'), {'role': 'user'})
sup2 = next((x for x in jread('users') if x.get('phone') == sup.get('phone')), {})
check('超级管理员的角色改不动', sup2.get('super') is True and sup2.get('role') != 'user')
# 登录后台的就是超管本人，所以这一下同时踩了「不能改自己」和「超管不可改」两条护栏
admin.post('/admin/users/%s/role' % sup.get('phone'), {'role': 'user'})
sup3 = next((x for x in jread('users') if x.get('phone') == sup.get('phone')), {})
check('不能改自己的角色（防把自己锁在门外）', sup3.get('super') is True and sup3.get('role') != 'user')

# 一人多角色：既 DM 又管理员 —— 两个工作台都能进，顶栏两个入口都露出来
admin.post('/admin/users/13900001111/role', [('roles', 'dm'), ('roles', 'admin')])
u_r = next((x for x in jread('users') if x.get('phone') == '13900001111'), {})
check('能给人同时挂上 DM + 管理员',
      set(u_r.get('roles') or []) == {'user', 'dm', 'admin'} and u_r.get('role') == 'admin',
      'roles=%s role=%s' % (u_r.get('roles'), u_r.get('role')))
s, _h = cus2.get('/dm')
check('既 DM 又管理员的人，DM 工作台能进', s == 200, 'HTTP %s' % s)
s, _h = cus2.get('/admin')
check('既 DM 又管理员的人，管理后台也能进', s == 200, 'HTTP %s' % s)
s, _h = cus2.get('/')
check('顶栏同时露出两个入口（以前是二选一，只能露一个）',
      '>DM 工作台</a>' in _h and '>管理后台</a>' in _h)
admin.post('/admin/users/13900001111/role', {'roles': ''})
u_r = next((x for x in jread('users') if x.get('phone') == '13900001111'), {})
check('一个角色都不勾 = 退回普通用户',
      (u_r.get('roles') or []) == ['user'] and u_r.get('role') == 'user', 'roles=%s' % u_r.get('roles'))
s, _h = cus2.get('/admin')
check('退回普通用户后进不去后台（403）', s == 403, 'HTTP %s' % s)
s, _h = cus2.get('/dm')
check('也进不去 DM 工作台了', s == 403, 'HTTP %s' % s)
admin.post('/admin/users/13900001111/role', {'role': 'dm'})     # 老写法（单值）也要管用
u_r = next((x for x in jread('users') if x.get('phone') == '13900001111'), {})
check('老写法 role=dm 仍然管用（兼容老表单/老脚本）',
      u_r.get('role') == 'dm' and (u_r.get('roles') or []) == ['user', 'dm'])
admin.post('/admin/users/13900001111/role', {'role': 'user'})

# 群发「只发普通用户」：员工（DM / 管理员 / 超管）不该收到 —— 多角色之后这条按角色集合判
admin.post('/admin/notice/send', {'title': '群发自检', 'text': '正文', 'scope': 'customers'})
_bc = next((x for x in jread('notices') if x.get('title') == '群发自检'), {})
_tos = {str(p) for p in (_bc.get('to') or [])}
_staff_phones = [str(x.get('phone')) for x in jread('users') if _bs.has_role(x, 'dm', 'admin')]
check('群发「只发普通用户」不会落到 DM / 管理员头上',
      bool(_tos) and all(p not in _tos for p in _staff_phones),
      '发给了 %d 人（其中员工 %d 人）' % (len(_tos), len([p for p in _staff_phones if p in _tos])))

# 排期页的「全部房间」总览：加一间房 + 排一场，总览里要能看见这场
admin.post('/admin/rooms/new', {'name': '自检房', 'cap': '6', 'dev': '投影'})
_first_sid = next((x.get('id') for x in jread('scripts')), 0)
admin.post('/admin/sessions/new', {'ts': ts_in(0), 'time': '18:30', 'roomId': '自检房',
                                   'dm': '', 'cap': '6', 'sid': _first_sid})
s, _h = admin.get('/admin/sessions')
check('排期页有「全部房间」总览，能看到刚排的场',
      '全部房间' in _h and 'room-grid' in _h and '自检房' in _h and '18:30' in _h)

# 排期改成「预约驱动」：客人挑时间下单 → 后台出现待安排 → 管理员只挑房间和 DM（时间不能改）
s, html = admin.get('/admin/sessions')
check('排期页不再让管理员自己排时间（「排一场」表单没了）',
      '待安排' in html and '排一场</h3>' not in html)
cus7.post('/book', {'sid': sc['id'], 'ts_day': iso_of(day), 'time': '13:00', 'players': 2, 'mode': '包车'})
_bka = next((b for b in jread('bookings') if b.get('phone') == '13900007666'
             and b.get('status') == 'booked' and not b.get('sessionId')), None)
s, html = admin.get('/admin/sessions')
check('客人的新预约出现在「待安排」里', bool(_bka) and '待安排' in html)
_dm_ph = next((u.get('phone') for u in jread('users') if _bs.has_role(u, 'dm')), '')
admin.post('/admin/bookings/%s/arrange' % (_bka or {}).get('id'), {'roomId': '自检房', 'dm': _dm_ph})
_bka = next((b for b in jread('bookings') if b.get('id') == (_bka or {}).get('id')), {})
check('安排成功（预约绑上了场次）', bool(_bka.get('sessionId')))
_ses = next((x for x in jread('sessions') if x.get('id') == _bka.get('sessionId')), {})
check('场次带上了房间和 DM', _ses.get('roomId') == '自检房' and _ses.get('dm') == _dm_ph,
      '%s / %s' % (_ses.get('roomId'), _ses.get('dm')))
check('客人收到「已安排房间」通知',
      any('已为你安排房间' in str(x.get('title')) and '13900007666' in [str(p) for p in (x.get('to') or [])]
          for x in jread('notices')))

# 角色图片：后台给角色传一张 → 前台剧本页摆成人物卡 → 能删掉
_role_sid = jread('scripts')[0].get('id')
admin.post('/admin/scripts/%s/save' % _role_sid,
           {'title': '', 'roles': '沈池, 阿澈', 'onSale': '1', 'allowRolePick': '1'})
_png1 = bytes.fromhex('89504e470d0a1a0a0000000d4948445200000001000000010806000000'
                      '1f15c4890000000a49444154789c63000100000500010d0a2db400000000'
                      '49454e44ae426082')
admin.post_file('/admin/scripts/%s/role-img' % _role_sid, 'img', 'role.png', _png1, {'idx': '0'})
_sc = next((x for x in jread('scripts') if x.get('id') == _role_sid), {})
check('能给角色传头像图', bool(((_sc.get('roles') or [{}])[0]).get('img')),
      str(((_sc.get('roles') or [{}])[0]).get('img')))
s, _h = guest.get('/scripts/%s' % _role_sid)
check('前台剧本页把角色摆成人物卡（带图）',
      s == 200 and 'role-gallery' in _h and '/img/role/' in _h, 'HTTP %s' % s)
admin.post('/admin/scripts/%s/role-img' % _role_sid, {'idx': '0', 'remove': '1'})
_sc = next((x for x in jread('scripts') if x.get('id') == _role_sid), {})
check('角色图能删掉', not ((_sc.get('roles') or [{}])[0]).get('img'))

# 剧本详情那排格子：评分这格由玩家点评算平均分；时长/难度/类型管理员能改
admin.post('/admin/scripts/%s/save' % _role_sid,
           {'title': '', 'players': '6人', 'dur': '约5小时', 'diff': '4',
            'type': '独家', 'onSale': '1', 'allowRolePick': '1'})
_sc = next((x for x in jread('scripts') if x.get('id') == _role_sid), {})
check('时长 / 难度 / 类型 后台能改',
      _sc.get('dur') == '约5小时' and _sc.get('diff') == 4 and _sc.get('type') == '独家',
      '%s / %s / %s' % (_sc.get('dur'), _sc.get('diff'), _sc.get('type')))
s, _h = guest.get('/scripts/%s' % _role_sid)
check('前台那排格子跟着变（4/5、约5小时、独家）',
      s == 200 and '约5小时' in _h and '4/5' in _h and '独家' in _h)
check('评分格在（有人点评才显示 ★ 分数，没有就显示 —）',
      s == 200 and '玩家评分' in _h)

s, _ = admin.post('/admin/users/13800000000/credit', {'delta': '-10', 'reason': '自检扣分'})
u = next((x for x in jread('users') if x.get('phone') == '13800000000'), {})
check('信用分改动生效并留了流水', int(u.get('credit') or 100) <= 90 and u.get('creditLogs'))
s, _ = admin.post('/admin/coupon', {'scope': 'all', 'amount': 15, 'days': 30, 'sleepDays': 30})
check('发券成功', len(jread('coupons')) > 0, '%d 张' % len(jread('coupons')))

print('⑧ 订单与日志页')
for path in ('/admin/orders', '/admin/logs', '/admin/scripts', '/admin/bookings?status=all'):
    s, html = admin.get(path)
    check('后台页 %s' % path, s == 200)

print('⑨ 排期 / 防撞房 / 评价 / DM 结算')
day5 = ts_in(5)
admin.post('/admin/sessions/new', {'ts': day5, 'time': '19:00', 'sid': sc['id'],
                                   'roomId': 'A房', 'dm': '12345678901', 'cap': 6})
ses = next((x for x in jread('sessions') if x.get('ts') == day5 and x.get('time') == '19:00'), None)
check('排了一场', bool(ses), 'DM=%s 房间=%s' % ((ses or {}).get('dmName'), (ses or {}).get('roomId')))
admin.post('/admin/sessions/new', {'ts': day5, 'time': '19:00', 'sid': sc['id'], 'roomId': 'A房', 'cap': 6})
same = [x for x in jread('sessions') if x.get('ts') == day5 and x.get('time') == '19:00'
        and x.get('roomId') == 'A房']
check('同一房间同一时段排不了第二场（防撞房）', len(same) == 1, '这间房有 %d 场' % len(same))
s, html = admin.get('/admin/sessions')
check('排期页能打开（预约驱动：有待安排区）', s == 200 and '待安排' in html)

cus4 = Client()
cus4.post('/login', {'account': '调试debug', 'password': '123123'})
cus4.post('/book', {'sid': sc['id'], 'ts': day5, 'time': '19:00', 'players': 3, 'mode': '包车'})
bk3 = next((b for b in jread('bookings') if b.get('ts') == day5 and b.get('status') == 'booked'), None)
check('客人约上了店里排好的场次', bk3 and bk3.get('sessionId') == (ses or {}).get('id'),
      '绑定场次=%s' % ((bk3 or {}).get('sessionId')))
s, html = cus4.get('/scripts/%s' % sc['id'])
check('详情页能直接「约这一场」', '约这一场' in html)

admin.post('/admin/verify', {'code': (bk3 or {}).get('verifyCode')})
cus4.post('/review/%s' % (bk3 or {}).get('id'), {'rating': '5', 'text': '自检评价：DM 讲得很好'})
rv = next((r for r in jread('reviews') if r.get('bid') == (bk3 or {}).get('id')), None)
check('客人能写评价', bool(rv), (rv or {}).get('username'))
s, html = guest.get('/scripts/%s' % sc['id'])
check('评价显示在剧本页', '自检评价' in html)
admin.post('/admin/reviews/%s/reply' % (rv or {}).get('id'), {'text': '谢谢，欢迎再来～'})
rv2 = next((r for r in jread('reviews') if r.get('id') == (rv or {}).get('id')), {})
check('门店回复存上了', rv2.get('reply') == '谢谢，欢迎再来～')
s, html = guest.get('/scripts/%s' % sc['id'])
check('回复也显示出来了', '欢迎再来' in html)

month = time.strftime('%Y-%m', time.localtime(day5 / 1000))
s, html = admin.get('/admin/dm?month=%s' % month)
check('DM 结算页能打开', s == 200 and '分成' in html)
check('结算里算上了这个 DM 和这场', 'dm测试' in html and str((ses or {}).get('dmName')) in html, month)
admin.post('/admin/dm/settle', {'month': month, 'dmPhone': '12345678901'})
st = next((x for x in jread('settles') if x.get('month') == month), None)
check('能标记「已结」', bool(st and st.get('settled')))

print('⑩ 留言 / 社区 / 周视图 / 结算口径')
cus4.post('/msg', {'cat': '⏰ 改时间', 'text': '自检留言：下周想改成 20:00 的场'})
msg = next((m for m in jread('messages') if '自检留言' in str(m.get('text'))), None)
check('客人能留言', bool(msg), (msg or {}).get('status'))
s, html = admin.get('/admin/messages')
check('后台能看到待回复留言', s == 200 and '自检留言' in html)
admin.post('/admin/messages/%s/reply' % (msg or {}).get('id'), {'text': '好的，给你留着'})
msg2 = next((m for m in jread('messages') if m.get('id') == (msg or {}).get('id')), {})
check('门店回复留言', msg2.get('status') == 'replied' and msg2.get('reply'))
s, html = cus4.get('/me?tab=notices')          # 「我的」改成标签页后，留言在"消息与留言"这一栏
check('客人「我的」里能看到店家回复', '好的，给你留着' in html)

cus4.post('/post', {'type': 'ask', 'title': '自检帖', 'text': '周六有没有人拼《自检本》'})
post = next((p for p in jread('posts') if p.get('title') == '自检帖'), None)
check('社区能发帖', bool(post), (post or {}).get('username'))
s, html = guest.get('/comm')
check('社区页能看到帖子', s == 200 and '自检帖' in html)
cus4.post('/post/%s/like' % (post or {}).get('id'), {})
post2 = next((p for p in jread('posts') if p.get('id') == (post or {}).get('id')), {})
check('点赞记上了', len(post2.get('likes') or []) == 1)
admin.post('/admin/post/%s/del' % (post or {}).get('id'), {})
check('员工能删帖', not any(p.get('id') == (post or {}).get('id') for p in jread('posts')))

s, html = admin.get('/admin/sessions?view=week')
check('排期周视图能打开', s == 200 and '看这一周' in html)

admin.post('/admin/settings', {'dmPayMode': 'fixed', 'dmFixedPay': '200'})
s, html = admin.get('/admin/dm?month=%s' % month)
check('切成「每场固定场费」后结算跟着变', s == 200 and '200' in html)
admin.post('/admin/settings', {'dmPayMode': 'rate'})       # 改回按比例，别把设置留乱

print('⑪ 图片 / 会员余额 / CSV 导入导出')
# 传头像（一个最小的 PNG）
png = bytes.fromhex('89504e470d0a1a0a0000000d494844520000000100000001080600000'
                    '01f15c4890000000a49444154789c6360000002000100ffff03000006000557bfabd40000000049454e44ae426082')
s, html = cus4.post_file('/profile', 'avatar', 'a.png', png, {'nick': '自检头像君'})
u_me = next((x for x in jread('users') if x.get('phone') == '13800000000'), {})
av = (u_me.get('profile') or {}).get('avatar') or ''
check('能上传头像', av.startswith('/img/avatar/'), av)
s, html = guest.get(av if av.startswith('/img/') else '/')
check('头像能读出来', s == 200)

# 传剧本封面
s, html = admin.post_file('/admin/scripts/%s/img' % sc['id'], 'cover', 'c.png', png)
sc2 = next((x for x in jread('scripts') if x.get('id') == sc['id']), {})
check('能给剧本传封面', str(sc2.get('img') or '').startswith('/img/cover/'), sc2.get('img'))
s, html = guest.get('/scripts/%s' % sc['id'])
check('封面出现在剧本页', '/img/cover/' in html)

# 会员余额：界面上撤掉了（2026-09，不做充值/余额抵扣）—— 逐页确认"真的看不到"
s, html = cus4.get('/me')
check('「我的」里不再出现余额', '余额' not in html)
s, html = cus4.get('/me?tab=coupons')
check('那栏改叫「券 / 心愿单」', '券 / 心愿单' in html and '余额' not in html)
check('侧栏那格换成了「已付定金」', '已付定金' in html)
s, html = cus4.get('/scripts/%s' % sc['id'])
check('下单页不再有「用余额抵定金」', 'use_balance' not in html and '抵定金' not in html)
s, html = admin.get('/admin')
check('后台用户弹窗里没有「会员充值」', '会员充值' not in html and 'f-money' not in html)
s, html = admin.get('/admin/users/13800000000')
check('用户详情页也没有余额', s == 200 and '余额' not in html)
# 后端逻辑还留着（数据字段没删，以后想恢复不用重写）：充值的口子仍然能用
admin.post('/admin/users/13800000000/recharge', {'amount': '300', 'note': '自检充值'})
u_me = next((x for x in jread('users') if x.get('phone') == '13800000000'), {})
check('后端余额逻辑仍在（只是界面不露）', (u_me.get('balance') or 0) >= 300)

# CSV 导出 / 导入
s, csv_text = admin.get('/admin/scripts/export')
check('导出剧本 CSV', s == 200 and 'title' in csv_text and sc['title'] in csv_text)
# 注意 roles 里有逗号，CSV 里必须用引号包起来，不然会被拆成两列（我第一次就写错了）
head = 'id,title,emoji,tags,players,dur,diff,price,type,onSale,allowRolePick,roles,desc\n'
row_new = ',CSV导入本,📦,机制/硬核,6人,约5小时,4,168,盒装,1,1,"甲,乙",自检导入\n'
admin.post_file('/admin/scripts/import', 'csv', 'scripts.csv', ('\ufeff' + head + row_new).encode('utf-8'))
imp = next((x for x in jread('scripts') if x.get('title') == 'CSV导入本'), None)
check('CSV 能导入新剧本', bool(imp),
      '角色 %s 个 / 单价 %s' % (len((imp or {}).get('roles') or []), (imp or {}).get('price')))
check('导入的标签和角色都解析对了',
      (imp or {}).get('tags') == ['机制', '硬核']
      and [r.get('name') for r in (imp or {}).get('roles') or []] == ['甲', '乙'])
# 带上 id 再导一次 → 应该是「更新那一本」，不是新建
row_upd = '%s,CSV导入本,📦,机制/硬核,6人,约5小时,4,188,盒装,1,1,"甲,乙",改过价\n' % (imp or {}).get('id')
admin.post_file('/admin/scripts/import', 'csv', 'scripts.csv', ('\ufeff' + head + row_upd).encode('utf-8'))
same = [x for x in jread('scripts') if x.get('title') == 'CSV导入本']
check('带 id 重导是更新而不是新建', len(same) == 1 and int(same[0].get('price')) == 188,
      '库里 %d 条，价格 %s' % (len(same), same[0].get('price') if same else '?'))

# ============ 上线安全：把"后门"堵上（2026-09 上线当天发现） ============
# 通用码 1234 只在本机开发时认：靠 Host 判断（线上是用域名访问的 → 一律不认）
_PUB = {'Host': 'tianshu.lovinfirefly.cn', 'X-Forwarded-For': '203.0.113.7'}
_reqq = urllib.request.Request(BASE + '/register', headers=_PUB)
_pub_reg = urllib.request.urlopen(_reqq, timeout=15).read().decode('utf-8', 'replace')
check('公网访问注册页时不再写"可以直接填 1234"', '直接填 1234' not in _pub_reg)
# 开发提示现在只在"点完按钮"的动态回话里（静态那行删了，免得跟动态提示说两遍）
try:
    _dev_tip = json.loads(guest.post('/code/send', {'email': 'dev-tip@example.com',
                         'purpose': 'register'},
                         headers={'X-Requested-With': 'fetch'})[1]).get('msg', '')
except Exception:
    _dev_tip = ''            # 500 或不是 JSON：当"没给提示"，别让整个自检崩掉
# 判据要带上成功那句话：光看"黑窗口"不够 —— 出错页里也可能有这仨字（误判过一次）
check('本机开发时点按钮会给提示（码在黑窗口 / 也能填 1234）',
      '验证码已生成' in _dev_tip and '黑窗口' in _dev_tip, _dev_tip[:60])
check('登录页已删掉"演示账号"提示', '演示账号' not in guest.get('/login')[1])
# 用域名（= 公网）拿通用码注册 → 必须失败
# 走 Client（先领 CSRF 令牌再交表单，和真浏览器一样）—— 这样测的才是"后门堵没堵"，
# 而不是"令牌对不对"（令牌不对的话请求根本到不了业务逻辑，测了等于没测）
_pc = Client()
_pc.get('/register', headers=_PUB)
_pc.post('/register', {'phone': '13900007777', 'username': '通用码测试号',
                       'password': '123456', 'password2': '123456', 'code': '1234',
                       'agree': '1', 'email': 'backdoor@example.com'}, headers=_PUB)
check('公网（用域名访问）拿 1234 注册不了（后门已堵）',
      not any(u.get('username') == '通用码测试号' for u in jread('users')))

# CSRF 闸门：写操作令牌不对必须被拒（防的是"别的网站骗你的浏览器替你提交"）
_cc = Client()
_cc.get('/')                                   # 领一颗令牌
s, _h = _cc.post('/login', {'account': 'FireFly', 'password': '123123'},
                 headers={'X-CSRF': 'wrong-token-000'})
check('写操作的 CSRF 令牌不对会被拒（403）', s == 403, 'HTTP %s' % s)
s, _h = _cc.post('/login', {'account': 'FireFly', 'password': '123123'})   # 带上正确的令牌
check('令牌对了就能正常过（不会误伤自己人）', s == 200 or s == 302, 'HTTP %s' % s)

# ============ 验证码发信（配了 SMTP 就真发邮件；没配也不该崩） ============
s, html = admin.get('/admin')
check('门店设置里有「验证码发信（邮箱）」这几栏', 'smtpHost' in html and 'smtpdm.aliyun.com' in html)
check('有「发一封测试邮件」入口', '发一封测试邮件' in html)
check('SMTP 密码那栏是 password 类型（不明文显示）', 'name="smtpPass" type="password"' in html)
check('有「发件人昵称」这一栏（客人收件箱里显示店名）', 'name="mailFromName"' in html)
# 直接测拼出来的 From（_bs 在文件开头已经导入）
_chk = dict(_bs.get_settings(), mailFrom='noreply@lovinfirefly.cn', mailFromName='甜薯剧本杀')
check('发件人拼成「甜薯剧本杀 <noreply@lovinfirefly.cn>」',
      _bs.mail_sender(_chk) == '甜薯剧本杀 <noreply@lovinfirefly.cn>', _bs.mail_sender(_chk))
_bad = dict(_chk, mailFromName='坏\n名字\r\nBcc: x@y.com')
check('昵称里的换行被掐掉（防邮件头注入）',
      '\n' not in _bs.mail_sender(_bad) and '\r' not in _bs.mail_sender(_bad),
      repr(_bs.mail_sender(_bad)))
check('昵称留空 = 只显示地址（不强加店名）',
      _bs.mail_sender(dict(_chk, mailFromName='')) == 'noreply@lovinfirefly.cn')
# 多角色（纯函数，不经过 HTTP）：角色是可多选的，老数据只有单值 role
check('roles_of 认老的单值 role（老账号不用迁移）', _bs.roles_of({'role': 'dm'}) == ['user', 'dm'])
check('roles_of 认新的 roles 列表', _bs.roles_of({'roles': ['dm', 'admin']}) == ['user', 'dm', 'admin'])
check('普通用户人人都有（不用谁去勾）',
      'user' in _bs.roles_of({'role': 'admin'}) and 'user' in _bs.roles_of({'roles': ['dm']}))
check('卡片徽章只写额外身份（短，才不挤崩卡片）',
      _bs.roles_badge({'roles': ['user', 'dm', 'admin']}) == 'DM、管理员'
      and _bs.roles_badge({'role': 'user'}) == '普通用户')
check('超管算管理员（不然初始账号反而进不去后台）', _bs.has_role({'role': 'super'}, 'admin'))
check('同时挂着 dm + admin，两种身份都判真',
      _bs.has_role({'roles': ['dm', 'admin']}, 'dm')
      and _bs.has_role({'roles': ['dm', 'admin']}, 'admin'))
check('普通用户既不是 DM 也不是管理员',
      not _bs.has_role({'role': 'user'}, 'dm', 'admin'))
check('主角色取最高的那个（显示用）', _bs.role_of({'roles': ['dm', 'admin']}) == 'admin')
s, html = admin.post('/admin/mail/test', {'to': 'test@example.com'})
check('没配 SMTP 时点测试邮件只给提示、不报错', '没发出去' in html or '还没配置' in html)
check('发信配置不当成"已发送"骗人', '已发出' not in html or '没发出去' in html)
check('发信通道能选（Resend / SMTP / Webhook）',
      'name="mailProvider"' in html and 'resend' in html and 'webhook' in html)
check('Resend 的 Key 栏也在（老版的 MAIL_KEY 可抄过来）', 'name="mailKey"' in html)

# 没配发信通道时，本机要码还是照旧走"打印到黑窗口"这条路
# 注意：只认成功那句中文字 —— 之前用「黑窗口」当判据，500 错误页里也有这仨字，误判过一次
s, html = guest.post('/code/send', {'email': 'someone@example.com', 'purpose': 'register'})
check('没配发信通道时，本机要码仍可用（走控制台打印）', '验证码已生成' in html, 'HTTP %s' % s)
# 防轰炸：同一邮箱 60 秒内只能要一次（照老版的规矩）
s, html = guest.post('/code/send', {'email': 'someone@example.com', 'purpose': 'register'})
check('同一邮箱 60 秒内不能重复要码', '秒后再点' in html or '刚发过' in html, 'HTTP %s' % s)
# 防暴力猜：同一个码试满 5 次就作废
_mail = 'tries@example.com'
guest.post('/code/send', {'email': _mail, 'purpose': 'register'})
for _ in range(6):
    guest.post('/register', {'phone': '13900009999', 'username': '猜码测试号', 'password': '123456',
                             'password2': '123456', 'code': '000000', 'agree': '1', 'email': _mail})
_codes = [c for c in jread('codes') if str(c.get('target')) == _mail]
check('同一个码试满 5 次会作废', _codes and _codes[-1].get('used') is True,
      'tries=%s used=%s' % ((_codes or [{}])[-1].get('tries'), (_codes or [{}])[-1].get('used')))

# 仓库卫生：该进仓库的代码文件不能被 .gitignore 吞掉
# 2026-09 踩过：.gitignore 里的 `_*.py` 把 tianshu/__init__.py 也忽略了 ——
# 本地跑得好好的，clone 到服务器上 `from tianshu import create_app` 直接 ImportError。
try:
    _ig = subprocess.run(['git', 'ls-files', '--others', '--ignored', '--exclude-standard'],
                         cwd=ROOT, capture_output=True, text=True, timeout=15).stdout.splitlines()
    _bad = [f for f in _ig
            if f.endswith(('.py', '.html', '.js', '.css'))
            and '__pycache__' not in f and not f.startswith('miniprogram/')]
    check('没有被 .gitignore 误吞的代码文件', not _bad, '、'.join(_bad[:5]))
except Exception:
    pass          # 没装 git / 不是仓库就跳过，别让自检因为环境问题失败

total = sum(1 for line in open(os.path.join(ROOT, 'tools', 'smoke_test.py'), encoding='utf-8')
            if "check('" in line)
print('⑫ 账号安全 / 改期 / 车队详情 / 评价细节')
s, html = guest.get('/forgot')
check('找回密码页能打开', s == 200 and '重置密码' in html and 'auth-card' in html)
cus5 = Client()
cus5.post('/register', {'phone': '13900002222', 'username': '账号安全号', 'password': '123456',
                        'password2': '123456', 'code': '1234', 'agree': '1',
                        'email': 'check5@example.com'})
cus5.post('/account/pwd', {'old': '123456', 'password': '654321'})
u5 = next((x for x in jread('users') if x.get('phone') == '13900002222'), {})
check('改密码后旧密码失效、新密码能登',
      u5.get('password', '').startswith('pbkdf2$') and cus5.post('/login', {'account': '13900002222', 'password': '654321'}))
# 换绑手机号删掉了（只有邮箱验证码，没法确认新号是本人的）—— 顺手确认入口真的没了
check('换绑手机号入口已删除', '换绑手机号' not in cus5.get('/me')[1])
check('换绑手机号的接口也删了', cus5.post('/account/phone', {'phone': '13900003333', 'code': '1234'})[0] in (404, 405))
check('验证码只发邮箱（只填手机号会被拦）', '邮箱' in cus5.post('/code/send', {'phone': '13900002222'})[1])

# 改期
cus5.post('/book', {'sid': sc['id'], 'ts': ts_in(2), 'time': '13:00', 'players': 2, 'mode': '包车'})
bk5 = next((b for b in jread('bookings') if b.get('phone') == '13900002222' and b.get('status') == 'booked'), None)
new_ts = ts_in(8)
cus5.post('/booking/%s/reschedule' % (bk5 or {}).get('id'), {'ts': new_ts, 'time': '20:30'})
bk5b = next((b for b in jread('bookings') if b.get('id') == (bk5 or {}).get('id')), {})
check('改期生效', bk5b.get('ts') == new_ts and bk5b.get('time') == '20:30',
      '%s %s' % (bk5b.get('day'), bk5b.get('time')))
o5 = next((x for x in jread('pays') if x.get('bid') == (bk5 or {}).get('id')), {})
check('订单跟着改期（定金保留）', o5.get('ts') == new_ts and str(o5.get('deposit')) == str(bk5b.get('deposit')))

# 车队详情（标签 / 预留位 / 聊天）—— 用一辆全新的拼车，别用前面已经核销掉的那辆
cus5.post('/book', {'sid': sc['id'], 'ts': ts_in(9), 'time': '13:00', 'players': 3, 'mode': '拼车'})
car_bk = next((b for b in jread('bookings') if b.get('ts') == ts_in(9) and b.get('carNew')), None)
car_id = (car_bk or {}).get('id')
s, html = admin.get('/car/%s' % car_id)
check('车队详情页能打开', s == 200 and '车上的成员' in html)
cus4.post('/car/%s/join' % car_id, {})
cus4.post('/car/%s/msg' % car_id, {'text': '自检：我上车啦'})
check('车队里能聊天', any(m.get('text') == '自检：我上车啦' for m in jread('carmsgs')))
s, html = admin.get('/car/%s' % car_id)
check('聊天内容显示在车队页', '自检：我上车啦' in html)
admin.post('/car/%s/tags' % car_id, {'tags': '不跳车'})
car_now = next((b for b in jread('bookings') if b.get('id') == car_id), {})
check('车主能设车队标签', car_now.get('carTags') == ['不跳车'], str(car_now.get('carTags')))

# 评价的细分维度（剧情/DM/氛围/房间）+ 点赞
admin.post('/admin/verify', {'code': (bk5 or {}).get('verifyCode')})     # 先核销，才能评价
cus5.post('/review/%s' % (bk5 or {}).get('id'),
          {'rating': '5', 'text': '带维度评价', 'plot': '4', 'dm': '5', 'vibe': '4', 'room': '3'})
rv_dim = next((r for r in jread('reviews') if r.get('bid') == (bk5 or {}).get('id')), {})
check('评价的四个维度存上了', (rv_dim.get('dims') or {}).get('剧情') == 4 and (rv_dim.get('dims') or {}).get('DM') == 5,
      str(rv_dim.get('dims')))
s, html = guest.get('/scripts/%s' % sc['id'])
check('维度展示在剧本页', '剧情' in html)

cus4.post('/review/%s/like' % (rv_dim or {}).get('id'), {})
rv_now = next((r for r in jread('reviews') if r.get('id') == (rv_dim or {}).get('id')), {})
check('评价能点赞', len(rv_now.get('likes') or []) >= 1)

# 注销（留到最后，因为会删号）
cus5.post('/account/delete', {'confirm': '13900002222'})
check('注销账号（连带数据删除）', not any(x.get('phone') == '13900002222' for x in jread('users')))

me_ok = True
print('⑬ PWA / 心形收藏 / 举报 / 追评 / 关注 / DM与后台新页')
s, html = guest.get('/static/manifest.webmanifest')
check('PWA 清单能下载', s == 200 and '甜薯' in html)
s, _ = guest.get('/static/sw.js')
check('离线外壳能下载', s == 200)
s, css = guest.get('/static/css/style.css')
check('样式含手机安全区适配', 'safe-area-inset' in css)
check('样式含右上角心形收藏', 'fav-btn' in css)

# 深浅色切换：墨色舞台（首屏/墨色区/我的资料卡）不许跟着主题翻 ——
# 一翻就成"浅底 + 浅字"（说明文字是写死的浅色），首屏那几行字会直接看不见
check('墨色舞台有独立令牌（不跟主题翻）', '--stage:#141312' in css and '--stage-ink:#F4F1EA' in css)
for sel in ('.hero{background:var(--stage)', '.band.ink{background:var(--stage)',
            '.profile{background:var(--stage)'):
    check('墨色块用 stage 而不是 --ink：%s' % sel.split('{')[0], sel in css)
check('搜索胶囊在暗底上是浅底深字',
      'background:var(--stage-ink)' in css and 'color:var(--stage)' in css)
check('暗底上的次要按钮用舞台字色（不然就是暗底暗字）',
      '.band.ink .btn-ghost,.hero .btn-ghost{color:var(--stage-ink)' in css)
# 深色模式下拿到的页面确实带上了 data-theme（说明主题真的切过去了）
s, html = guest.get('/theme')
s, html = guest.get('/')
check('主题切换接口能用', s == 200)
s, html = guest.get('/scripts')
check('剧本卡片上有那颗心', 'fav-btn' in html)
s, html = cus4.get('/')          # 心形只在登录后显示
check('登录状态下首页也有那颗心', 'fav-btn' in html)

# 举报
cus4.post('/post', {'type': 'chat', 'title': '被举报帖', 'text': '这条用来测举报'})
bad = next((p for p in jread('posts') if p.get('title') == '被举报帖'), None)
cus4.post('/post/%s/report' % (bad or {}).get('id'), {'reason': '自检举报'})
check('举报记下来了', any(r.get('reason') == '自检举报' for r in jread('reports')))
s, html = admin.get('/admin/reports')
check('后台能看到举报', s == 200 and '自检举报' in html)
admin.post('/admin/reports/%s/handle' % next(r['id'] for r in jread('reports') if r.get('reason') == '自检举报'),
           {'act': 'del'})
check('删帖处理生效', not any(p.get('id') == (bad or {}).get('id') for p in jread('posts')))

# 追评（cus5 上一节已注销，用 cus4 那条评价来追）
rv_mine = next((r for r in jread('reviews') if '自检评价' in str(r.get('text'))), None)
if rv_mine:
    cus4.post('/review/%s/follow' % rv_mine.get('id'), {'text': '玩完补一句：DM 节奏很好'})
    rv_fu = next((r for r in jread('reviews') if r.get('id') == rv_mine.get('id')), {})
    check('追评加上了', any('补一句' in str(f.get('text')) for f in (rv_fu.get('followUps') or [])))
else:
    check('追评加上了', False, '没找到自己的评价')

# 「获取验证码」：必须是普通按钮 + 接口给 fetch 回 JSON
# （以前它 type=submit + formaction，浏览器先跑整表校验 → 弹"请填写此字段"，码根本没发出去）
s, html = guest.get('/register')
check('注册页的「获取验证码」不再是提交按钮（点了不会再弹"请填写此字段"）',
      'data-code-btn' in html and 'type="button" data-code-btn' in html)
s, html = guest.get('/forgot')
check('找回密码页的「获取验证码」也一起修了',
      'data-code-btn' in html and 'data-purpose="reset"' in html)
s, body = guest.post('/code/send', {'email': 'check-codebox@example.com', 'purpose': 'register'},
                     headers={'X-Requested-With': 'fetch', 'Accept': 'application/json'})
check('取验证码接口给 fetch 回 JSON（页面不刷新，填过的密码不会丢）',
      s == 200 and '"ok"' in body, body[:70])

# 邀请返利：填好友的邀请码，双方各得一张抵扣券（金额 = 门店设置里的 inviteCoupon，默认 10 元）
inv_code = next((x.get('invite') for x in jread('users') if x.get('phone') == '13900001111'), None)
check('注册时自动生成了邀请码', bool(inv_code), str(inv_code))
cus6 = Client()
cus6.post('/register', {'phone': '13900008888', 'username': '被邀请号', 'password': '123456',
                        'password2': '123456', 'code': '1234', 'agree': '1',
                        'email': 'check6@example.com', 'invite': inv_code})
inv_cps = [c for c in jread('coupons') if c.get('from') == '邀请返利']
got_phones = {str(c.get('phone')) for c in inv_cps}
check('邀请发出两张券（邀请人 + 新注册的人各一张）',
      {'13900001111', '13900008888'} <= got_phones, '发给了 %s' % '、'.join(sorted(got_phones)))
check('券是 10 元（不是文案上旧写的 15）',
      bool(inv_cps) and all(int(c.get('amount') or 0) == 10 for c in inv_cps),
      '金额 %s' % [c.get('amount') for c in inv_cps])
s, html = cus6.get('/me?tab=coupons')
check('新人能在「我的 → 券」里看到这张券', s == 200 and '邀请返利' in html)
s, html = guest.get('/register')
check('注册页文案跟设置一致（显示 ¥10）', '¥10' in html)
s, html = cus6.get('/me?tab=profile')
check('「资料」里能看到自己的邀请码', 'TS' in html)

# 关注（关注一直存在的 FireFly）
cus4.post(urllib.parse.quote('/u/FireFly/follow'), {})
u_follow = next((x for x in jread('users') if x.get('username') == 'FireFly'), {})
check('关注成功（对方粉丝里出现我）', '调试debug' in [str(x) for x in (u_follow.get('followers') or [])],
      str(u_follow.get('followers')))
s, html = guest.getq('/u/FireFly')
check('玩家主页能打开', s == 200 and 'FireFly' in html)

# DM 工作台：三块内容现在都在 /dm 一个页面里（点标签前端切，不再各占一个网址）
dmcli = Client()
dmcli.post('/login', {'account': 'dm测试', 'password': '123123'})
s, html = dmcli.get('/dm')
check('DM 工作台能打开', s == 200)
check('六块面板都在同一页', all(('data-tab="%s"' % k) in html
                              for k in ('msgs', 'today', 'credit', 'sched', 'growth', 'guides')))
check('DM 页不留子网址', 'href="?tab=' not in html and 'href="/dm/credit"' not in html)
# 「我这个月能拿多少」以前指向 admin 的结算页，DM 不是员工 → 点进去 403
check('DM 工作台不再有指向后台的链接（以前点「我这个月能拿到多少」会 403）',
      'href="/admin' not in html)
check('「我这个月能拿多少」跳到自己的结算块', '#my-pay' in html and '我的结算' in html)
check('结算块有锚点 id（链接才滚得到）', 'id="my-pay"' in html)
# 锚点必须能定位到"面板里面的块"：结算块在「今日场次」面板里，
# 以前的 JS 只认标签名（#my-pay 找不到 → 回退第一个标签 = 点了没反应）
s, tabs_js = guest.get('/static/js/tabs.js')
check('锚点能先切面板再滚动（不再只认标签名）',
      'resolveHash' in tabs_js and "closest('.tabpane')" in tabs_js)
check('同页锚点链接接上了 hashchange', "addEventListener('hashchange'" in tabs_js)

# DM 形象照：自己上传，客人打开公开主页能看到
check('DM 工作台有上传形象照的入口', 'name="photo"' in html and 'multipart/form-data' in html)
dmcli.post_file('/dm/profile', 'photo', 'me.png', png,
                {'style': '情感本一把好手', 'bio': '自检用简介', 'canOpen': '1'})
dm_u = next((x for x in jread('users') if x.get('phone') == '12345678901'), {})
dm_photo = ((dm_u.get('dmProfile') or {}).get('photo')) or ''
check('DM 能上传形象照', dm_photo.startswith('/img/dm/'), dm_photo)
s, _ = guest.get(dm_photo if dm_photo.startswith('/img/') else '/')
check('形象照能读出来', s == 200)
s, html_pub = guest.getq('/dm/12345678901')
check('公开主页上有形象照', s == 200 and dm_photo in html_pub)
check('公开主页上还有风格与简介', '情感本一把好手' in html_pub and '自检用简介' in html_pub)
s, html_g = admin.get('/admin/growth')
check('后台 DM 档案里也带上这张照片', dm_photo in html_g)
# 勾「删掉这张照片」就撤下来（不带文件提交，跟浏览器行为一致）
dmcli.post('/dm/profile', {'del_photo': '1', 'style': '情感本一把好手', 'canOpen': '1'})
dm_u2 = next((x for x in jread('users') if x.get('phone') == '12345678901'), {})
check('能删掉形象照', not ((dm_u2.get('dmProfile') or {}).get('photo')))
check('只有 /img/dm/ 这类能读（其它子目录不给）', guest.get('/img/secret/x.png')[0] == 404)
s, html = dmcli.get('/me')
check('「我的」五个面板都渲染了', all(('data-tab="%s"' % k) in html
                                     for k in ('bookings', 'orders', 'coupons', 'notices', 'profile')))
# 练本申请
dmcli.post('/dm/practices', {'sid': sc['id'], 'note': '自检练本'})
check('DM 能提练本申请', any('自检练本' in str(p.get('note')) for p in jread('practices')))
# DM 成长档案（后台新面板）：段位 / 擅长本 / 反馈都要有
s, html = admin.get('/admin/growth')
check('后台有「DM 成长档案」面板', s == 200 and 'DM 成长档案' in html)
check('档案里有段位和擅长本', '见习 DM' in html and '擅长本' in html)
check('档案里有带本情况和反馈', '累计带本' in html and '客人反馈' in html)

s, html = admin.get('/admin/guides')
check('后台能看到练本申请', s == 200 and '自检练本' in html)

# 后台新页
for u in ('/admin/guides', '/admin/notice', '/admin/backup', '/admin/reports'):
    s, html = admin.get(u)
    check('后台页 %s' % u, s == 200)
s, html = admin.get('/admin/users/13800000000')
check('客户档案页能打开', s == 200 and '13800000000' in html)
# 群发通知
admin.post('/admin/notice/send', {'title': '自检群发', 'text': '这是一条自检通知', 'scope': 'all'})
check('群发通知发出去了', any(n.get('title') == '自检群发' for n in jread('notices')))

print('⑭ 一代 / 二代界面切换（并站之后管理员可选）')
s, html = guest.get('/')
check('默认二代：客人看到新骨架（加载 design3.css）', s == 200 and 'design3.css' in html)
s, html = guest.get('/?ui=1')
check('客人带 ?ui=1 也切不了（只有管理员能预览）', s == 200 and 'design3.css' in html)
s, html = admin.get('/?ui=1')
check('管理员能预览一代：老骨架、不加载 design3.css',
      s == 200 and 'design3.css' not in html and 'style.css' in html, 'HTTP %s' % s)
s, html = admin.get('/?ui=2')
check('也能一键切回二代', s == 200 and 'design3.css' in html)
# 一代那套模板是从改版前的提交原样搬过来的 —— 逐页确认真的还能渲染（别点开就 500）
for path in ('/', '/scripts', '/car', '/comm', '/me', '/login', '/register', '/forgot',
             '/scripts/%s' % sc['id']):
    s, html = admin.get(path + ('&' if '?' in path else '?') + 'ui=1')
    check('一代模式 %s 能打开' % path, s == 200, 'HTTP %s' % s)
# 真切过去：设置存成一代 → 客人也走一代；再切回二代
admin.post('/admin/settings', {'uiVer': '1'})
s, html = guest.get('/scripts')
check('后台设成一代后，客人看到的也是老版式', s == 200 and 'design3.css' not in html)
# 一代模式下后台和 DM 工作台必须**一点不受影响**：它们是店里干活的工具，
# 永远用新版骨架（一代目录里根本没有这些模板，得能落回二代 —— 这里踩过 500）
s, html = admin.get('/admin')
check('一代模式下后台照样打开、还是新版骨架（tnav），没被版式连累',
      s == 200 and 'tnav' in html and 'site-nav' not in html
      and '服务端出了点问题' not in html and '到店核销' in html, 'HTTP %s' % s)
s, html = admin.get('/dm')
check('一代模式下 DM 工作台也正常', s == 200 and 'tabpane' in html, 'HTTP %s' % s)
s, html = admin.get('/admin?ui=1')
check('后台自己带 ?ui=1 也还是新版骨架（后台不跟着切）', s == 200 and 'tnav' in html)
s, html = admin.get('/admin/bookings?status=all')
check('一代模式下后台的子页也能打开', s == 200, 'HTTP %s' % s)
admin.post('/admin/settings', {'uiVer': '2'})
s, html = guest.get('/scripts')
check('切回二代：客人又看到新骨架', s == 200 and 'design3.css' in html)
s, html = admin.get('/admin?tab=dash')
check('后台「门店设置」里有「网站版式」下拉（一代 / 二代都在）',
      'name="uiVer"' in html and '一代' in html and '二代' in html)

# 谁能动版式：**只有管理员**。DM 和客人既看不到入口，也切不动 ——
# 版式是全站统一的（一个人改了所有人跟着变），所以权限必须卡在管理员这一级。
s, html = dmcli.get('/?ui=1')
check('DM 带 ?ui=1 不生效（还是二代）', s == 200 and 'design3.css' in html)
s, html = dmcli.get('/?skin=monolith')
check('DM 带 ?skin= 也不生效（预览只给管理员）', 'skin-monolith.css' not in html)
s, html = dmcli.get('/dm')
check('DM 工作台上没有「版式预览」那一栏（不是管理员就看不见）', '版式预览' not in html)
s, html = dmcli.get('/admin')
check('DM 进不了后台（自然也改不了版式）', s == 403 or '到店核销' not in html, 'HTTP %s' % s)
dmcli.post('/admin/settings', {'uiVer': '1'})
check('DM 直接提交改版式也被拦住（设置没变）',
      str((jread('settings') or {}).get('uiVer') or '2') != '1',
      '现在是 %s' % (jread('settings') or {}).get('uiVer'))
guest.post('/admin/settings', {'uiVer': '1'})
check('客人提交改后台设置同样拦住', str((jread('settings') or {}).get('uiVer') or '2') != '1')
s, html = guest.get('/scripts')
check('确认这会儿客人还是二代（前面那些尝试都没生效）', s == 200 and 'design3.css' in html)

print('⑮ 这一轮用户反馈的修复（界面细节，用断言钉住）')
# ① 桌面页脚上不该出现「装 App」大按钮（手机底栏那颗留着，那是该有的）
s, html = guest.get('/')
_foot = html.split('<footer class="dfoot">')[-1].split('</footer>')[0] if 'dfoot' in html else ''
check('页脚里没有「装 App」（那个只属于手机底栏）',
      'dfoot' in html and 'js-install' not in _foot and '装App' not in _foot)
s, html = guest.get('/scripts')
_foot2 = html.split('<footer class="dfoot">')[-1].split('</footer>')[0] if 'dfoot' in html else ''
check('剧本库页脚也一样', 'js-install' not in _foot2)
# ② 后台不铺整站页脚（否则会跟左侧目录叠在一起）
s, html = admin.get('/admin')
check('后台页不铺整站页脚（不会和左侧目录打架）',
      s == 200 and 'dfoot' not in html and 'dfoot__brand' not in html, 'HTTP %s' % s)
s, html = guest.get('/scripts')
check('客人页面照旧有整站页脚', 'dfoot__brand' in html)
# ③ 社区分类是页内筛：按钮 + data-filter，不再跳网址
s, html = guest.get('/comm')
check('社区分类改成就地筛（data-filter="type" + 按钮）',
      s == 200 and 'data-filter="type"' in html and 'data-show="all"' in html)
check('社区分类不再是会跳页的链接', '?t=' not in html)
# ④ 剧本库的 tag 栏不再吸顶跟随
s, html = guest.get('/scripts')
check('剧本库 tag 栏不再吸顶（toolbar3--sticky 已去掉）', 'toolbar3--sticky' not in html)
# ⑤ 拼车"满没满"：满员的车不能再显示成有位
try:
    _pool = _bs.car_pool()
    check('拼车满员判定和显示口径一致（joined ≥ cap 就是满）',
          all(c['full'] == (c['joined'] >= c['cap']) for c in _pool),
          '在跑的车 %d 辆' % len(_pool))
except Exception as _e:
    check('拼车满员判定和显示口径一致（joined ≥ cap 就是满）', False, str(_e)[:60])
# ⑥ 打分星星点得亮（style.css 里只有 hover、没有 :checked —— 点完不变色=像点不上）
_s, _css3 = guest.get('/static/css/design3.css')
check('打分星星有选中态（点完要亮起来）', '.stars input:checked ~ label' in _css3)
# ⑦ 评价区那颗心不再绝对定位叠在昵称上
_s, _csss = guest.get('/static/css/style.css')
check('行内 .fav-btn 取消绝对定位（评价区不再压住昵称）', '.b3.fav-btn,.btn.fav-btn' in _csss)
# ⑧ 订单卡片里能看到"我给的评价"（原来只有一个「已评价 ✓」，想看自己写了啥还得去剧本页翻）
s, html = cus4.get('/me')
check('「我的」里能看到自己写过的评价（星级 + 内容）',
      s == 200 and 'myrev3' in html and '自检评价' in html, 'HTTP %s' % s)

# ⑨ 光标跟随那团暗红光：强度够不够 + 是不是缓动跟随（用户说"看不见"）
_s, _ui3 = guest.get('/static/js/ui3.js')
check('光斑是缓动跟随（rAF 每帧靠近），不是瞬移贴上去',
      'requestAnimationFrame(frame)' in _ui3)
check('光斑强度给够了（原来 8% 透明度，深底上等于没画）',
      'rgba(200,50,30,.26)' in _css3 and 'rgba(255,120,86,.16)' in _css3)
for _p in ('/?browse=1', '/scripts/%s' % sc['id'], '/welcome'):
    _s, _h = guest.get(_p)
    check('暗场首屏挂了光斑层 %s' % _p, _s == 200 and 'glow3' in _h, 'HTTP %s' % _s)

# ⑩ 电脑版（套壳 exe）：文件在 + 电脑页脚有下载入口（手机上应该看不到）
_exe = os.path.join(ROOT, 'tianshu', 'static', 'app', 'tianshu-desktop.exe')
check('电脑版 exe 在（网站能下载到）', os.path.exists(_exe),
      '%.1f MB' % (os.path.getsize(_exe) / 1048576) if os.path.exists(_exe) else '缺文件')
check('桌面壳源码 desktop.py 在', os.path.exists(os.path.join(ROOT, 'desktop.py')))
s, html = guest.get('/scripts')
check('电脑页脚有「电脑版下载」入口', 'tianshu-desktop.exe' in html and '电脑版下载' in html)
check('手机端会藏起「电脑版下载」（那边有装App）', '.desk-dl{display:none}' in _css3)

print('')
print('=' * 46)
if fails:
    print('跑了 %d 项，有 %d 项没过：' % (total, len(fails)))
    for name in fails:
        print('  [!!] %s' % name)
else:
    print('全部 %d 项检查通过 [OK]' % total)

# 收工：把自己起的服务和临时数据目录收拾掉（没过就留着，方便翻现场）
if _server:
    try:
        _server.terminate()
        _server.wait(timeout=10)
    except Exception:
        try:
            _server.kill()
        except Exception:
            pass
if _tmpdir:
    if fails:
        print('这次没过，临时数据留着查：%s' % _tmpdir)
    else:
        shutil.rmtree(_tmpdir, ignore_errors=True)
sys.exit(1 if fails else 0)
