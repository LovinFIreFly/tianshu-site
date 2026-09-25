# -*- coding: utf-8 -*-
"""
自检脚本：改完代码跑一遍，看看有没有把功能改坏

用法（两个窗口）：
    python app.py --no-browser       # 第一个窗口起服务
    python tools/smoke_test.py       # 第二个窗口跑自检

它会真的去点网页：登录、加剧本、下单、核销、退款、拼车、权限，
顺便直接读 data/*.json 核对算出来的钱对不对。
"""
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get('BASE', 'http://127.0.0.1:8000')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')

# 中文控制台（GBK）里 ✓ 这种符号会报错，兜底成问号，别让自检自己先挂了
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors='replace')
    except Exception:
        pass

fails = []


def check(name, ok, extra=''):
    print(('  ✓ ' if ok else '  ✗ ') + name + (('  ' + str(extra)) if extra else ''))
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

    def get(self, path):
        try:
            with self.op.open(BASE + path, timeout=15) as r:
                return r.status, r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8', 'replace')

    def post(self, path, data=None):
        body = urllib.parse.urlencode(data or {}).encode('utf-8')
        req = urllib.request.Request(BASE + path, data=body, method='POST')
        try:
            with self.op.open(req, timeout=15) as r:
                return r.status, r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8', 'replace')


def ts_in(days):
    """N 天后那一天的 0 点（毫秒）"""
    t = time.localtime(time.time() + days * 86400)
    return int(time.mktime(time.strptime(time.strftime('%Y-%m-%d', t), '%Y-%m-%d'))) * 1000


print('① 公开页面')
guest = Client()
for path, want in (('/', '剧本'), ('/scripts', '剧本库'), ('/car', '拼车'), ('/login', '登录'), ('/register', '注册')):
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
s, _ = cus.post('/book', {'sid': sc['id'], 'ts': day, 'time': '19:00', 'players': 4,
                          'mode': '拼车', 'role': '阿甲'})
bk = next((b for b in jread('bookings') if b.get('sid') == sc['id'] and b.get('ts') == day
           and b.get('status') == 'booked'), None)
check('下单成功', bool(bk), (bk or {}).get('verifyCode'))
check('定金 = 总价 × 30%', bk and bk.get('deposit') == round(int(bk.get('amount') or 0) * 0.3),
      '%s × 30%% = %s' % ((bk or {}).get('amount'), (bk or {}).get('deposit')))
check('核销码是 6 位', bk and len(str(bk.get('verifyCode'))) == 6)
check('选角记上了', bk and bk.get('role') == '阿甲')
# 同一个角色第二个人不能选
cus2 = Client()
cus2.post('/register', {'phone': '13900001111', 'username': '自检小号', 'password': '123456'})
cus2.post('/book', {'sid': sc['id'], 'ts': day, 'time': '19:00', 'players': 2, 'mode': '拼车', 'role': '阿甲'})
dup = [b for b in jread('bookings') if b.get('role') == '阿甲' and b.get('ts') == day
       and b.get('status') == 'booked']
check('同一角色不会被两个人选走', len(dup) == 1, '有 %d 条' % len(dup))
s, html = cus.get('/me')
check('「我的」能看到预约和核销码', s == 200 and str(bk.get('verifyCode')) in html)

print('④ 拼车大厅（要在核销之前测，核销后这车就不在池子里了）')
s, html = guest.get('/car')
check('车上出现了这个本', title in html)
cus3 = Client()
cus3.post('/login', {'account': '13900001111', 'password': '123456'})
s, _ = cus3.post('/car/%s/join' % bk.get('id'), {})
joined = [b for b in jread('bookings') if b.get('carOwner') == bk.get('username')
          and b.get('sid') == sc['id'] and b.get('status') == 'booked']
check('别人能上车', len(joined) >= 1, '车里 %d 人（含车主）' % (len(joined) + 1))

print('⑤ 员工：到店核销')
s, html = admin.post('/admin/verify', {'code': bk.get('verifyCode')})
after = next((b for b in jread('bookings') if b.get('id') == bk.get('id')), {})
check('核销成功', after.get('status') == 'arrived', '状态=%s' % after.get('status'))
s, html = admin.post('/admin/verify', {'code': '000000'})
check('乱输码会提示查不到', '查不到' in html or '无效' in html or '失败' in html)
s, html = guest.get('/car')
check('核销后这车就从拼车池里撤了', title not in html)

print('⑥ 定金与退款规则')
o = next((x for x in jread('pays') if x.get('bid') == bk.get('id')), None)
check('下单自动生成了待付订单', o and o.get('status') == 'unpaid', (o or {}).get('status'))
s, _ = cus.post('/order/%s/pay' % o['id'], {})
o = next((x for x in jread('pays') if x.get('id') == o['id']), {})
check('付定金', o.get('status') == 'paid')
# 再来一单（3 天后，够免费取消）然后退掉
cus.post('/book', {'sid': sc['id'], 'ts': ts_in(4), 'time': '20:00', 'players': 2, 'mode': '包车'})
bk2 = next((b for b in jread('bookings') if b.get('sid') == sc['id'] and b.get('ts') == ts_in(4)
            and b.get('status') == 'booked'), None)
o2 = next((x for x in jread('pays') if x.get('bid') == (bk2 or {}).get('id')), None)
cus.post('/order/%s/pay' % (o2 or {}).get('id'), {})
s, html = cus.post('/order/%s/refund' % (o2 or {}).get('id'), {})
o2 = next((x for x in jread('pays') if x.get('id') == (o2 or {}).get('id')), {})
check('提前 4 天取消 → 全额退定金', o2.get('status') == 'refunded', '状态=%s' % o2.get('status'))

print('⑦ 客户档案 / 发券')
s, html = admin.get('/admin/users')
check('客户列表能看到人', s == 200 and '调试debug' in html)
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
check('排期页能打开', s == 200 and '排一场' in html)

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

print('')
print('=' * 46)
if fails:
    print('有 %d 项没过：%s' % (len(fails), '、'.join(fails)))
else:
    print('全部检查通过 ✓')
sys.exit(1 if fails else 0)
