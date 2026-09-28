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
import subprocess
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
                                     headers={'Content-Type': 'multipart/form-data; boundary=%s' % bd})
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
# 用页面特征判断（空库时首页的引导卡里也会出现"账号登录"字样，别拿它当判据）
check('点「先随便逛逛」能进门店首页',
      s == 200 and '沉浸式剧本体验' not in html and '拼车' in html)
g2 = Client()                    # 另一个"没点过逛逛、但已经逛过剧本库"的游客
g2.get('/scripts')
s, html = g2.get('/')
check('已经在站里逛的人，回首页不会再被欢迎页挡住',
      s == 200 and '沉浸式剧本体验' not in html)
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
check('拼车定金统一 ¥50（跟人数、总价都无关）',
      bk and int(bk.get('deposit') or 0) == 50, '定金 ¥%s' % (bk or {}).get('deposit'))
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
s, _ = admin.post('/admin/orders/%s/confirm' % o['id'], {})   # 管理员确认到账
o = next((x for x in jread('pays') if x.get('id') == o['id']), {})
check('管理员点「确认支付定金」', o.get('status') == 'paid', '状态=%s' % o.get('status'))
s, html = cus.get('/me')
check('确认之后客人才看得到核销码', s == 200 and str(bk.get('verifyCode')) in html)
s, html = admin.get('/admin/bookings?status=all')
check('管理员/后台一直能看到核销码', str(bk.get('verifyCode')) in html)

# 包车还是按比例算定金（一口价只给拼车）
cus.post('/book', {'sid': sc['id'], 'ts': ts_in(4), 'time': '20:00', 'players': 2, 'mode': '包车'})
bk2 = next((b for b in jread('bookings') if b.get('sid') == sc['id'] and b.get('ts') == ts_in(4)
            and b.get('status') == 'booked'), None)
check('包车定金仍按比例（总价 × 30%）',
      bk2 and int(bk2.get('deposit') or 0) == round(int(bk2.get('amount') or 0) * 0.3),
      '%s × 30%% = %s' % ((bk2 or {}).get('amount'), (bk2 or {}).get('deposit')))
o2 = next((x for x in jread('pays') if x.get('bid') == (bk2 or {}).get('id')), None)
cus.post('/order/%s/pay' % (o2 or {}).get('id'), {})       # 前台现金收的，可以直接标已付
s, html = cus.post('/order/%s/refund' % (o2 or {}).get('id'), {})
o2 = next((x for x in jread('pays') if x.get('id') == (o2 or {}).get('id')), {})
check('提前 4 天取消 → 全额退定金', o2.get('status') == 'refunded', '状态=%s' % o2.get('status'))

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
check('本机开发时还留着那句提示（本地好用）', '本机开发也可以直接填 1234' in guest.get('/register')[1])
check('登录页已删掉"演示账号"提示', '演示账号' not in guest.get('/login')[1])
# 用域名（= 公网）拿通用码注册 → 必须失败
_body = urllib.parse.urlencode({'phone': '13900007777', 'username': '通用码测试号',
                                'password': '123456', 'password2': '123456', 'code': '1234',
                                'agree': '1', 'email': 'backdoor@example.com'}).encode()
_reqp = urllib.request.Request(BASE + '/register', data=_body, method='POST', headers=_PUB)
try:
    urllib.request.urlopen(_reqp, timeout=15).read()
except Exception:
    pass
check('公网（用域名访问）拿 1234 注册不了（后门已堵）',
      not any(u.get('username') == '通用码测试号' for u in jread('users')))

# ============ 验证码发信（配了 SMTP 就真发邮件；没配也不该崩） ============
s, html = admin.get('/admin')
check('门店设置里有「验证码发信（邮箱）」这几栏', 'smtpHost' in html and 'smtpdm.aliyun.com' in html)
check('有「发一封测试邮件」入口', '发一封测试邮件' in html)
check('SMTP 密码那栏是 password 类型（不明文显示）', 'name="smtpPass" type="password"' in html)
s, html = admin.post('/admin/mail/test', {'to': 'test@example.com'})
check('没配 SMTP 时点测试邮件只给提示、不报错', '没发出去' in html or '还没配置' in html)
check('发信配置不当成"已发送"骗人', '已发出' not in html or '没发出去' in html)
# 没配 SMTP 时，本机要码还是照旧走"打印到黑窗口"这条路
# 注意：只认成功那句中文字 —— 之前用「黑窗口」当判据，500 错误页里也有这仨字，误判过一次
s, html = guest.post('/code/send', {'email': 'someone@example.com', 'purpose': 'register'})
check('没配发信邮箱时，本机要码仍可用（走控制台打印）', '验证码已生成' in html, 'HTTP %s' % s)

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

print('')
print('=' * 46)
if fails:
    print('跑了 %d 项，有 %d 项没过：' % (total, len(fails)))
    for name in fails:
        print('  [!!] %s' % name)
else:
    print('全部 %d 项检查通过 [OK]' % total)
sys.exit(1 if fails else 0)
