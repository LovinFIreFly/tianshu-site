# -*- coding: utf-8 -*-
"""
员工后台：核销、预约管理、客户（信用分/拉黑/充值/发券）、剧本、订单、设置、日志

权限靠 staff_required（管理员和超管能进；DM 也能看一部分，按需再加）。
后台是"破坏性操作"最多的地方：拉黑、清数据、改价 —— 改这儿的东西动手前想一下。
"""
import os
import time

import secrets

from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for

from tianshu import business
from tianshu.db import db
from tianshu.security import current_user, dm_required, is_staff, role, staff_required
from config import DATA_DIR, SESSION_TIMES, TAG_PRESETS

bp = Blueprint('admin', __name__, url_prefix='/admin')


def dash_panel():
    """概览面板：今天几场、待核销、最近预约、操作日志"""
    bookings = db.rows('bookings')
    st = business.stats()
    today0 = business.day_label(business.now_ms())
    return render_template('admin/panel_dash.html',
                           stat=st, sessions=business.today_sessions(),
                           pending=[b for b in bookings if b.get('status') == 'booked'
                                    and b.get('day') == today0][:10],
                           recent=sorted(bookings, key=lambda x: -(x.get('id') or 0))[:8],
                           logs=db.rows('logs')[:6],
                           users=db.rows('users'), scripts=db.rows('scripts'))


def _panel_html(key):
    """把某个面板渲染成一段 HTML —— 外壳页面要把它塞进 <div class="tabpane">"""
    r = _TAB_FUNCS[key]()
    return r.get_data(as_text=True) if hasattr(r, 'get_data') else str(r)


@bp.get('/')
@staff_required
def dashboard():
    """管理后台 —— 唯一的入口页。

    14 个面板在这一次全渲染好，点标签只是前端切显示：不跳页、不改网址、点了就到
    （老版 index.html 就是这么干的）。所以不管点哪个功能，网址永远停在 /admin。
    """
    return render_template('admin/index.html', panels={k: _panel_html(k) for k in _TAB_FUNCS})


@bp.get('/<path:old>')
@staff_required
def legacy(old):
    """老网址（/admin/bookings 之类）送回 /admin，用 #标签 打开对应面板。
    留着纯粹是为了以前存的书签还能点开。"""
    return redirect(url_for('admin.dashboard') + '#' + old.split('/')[0])


@bp.post('/verify')
@staff_required
def verify():
    """到店核销：客人报 6 位码，前台在这儿输一下"""
    ok, msg, _b = business.verify_checkin(request.form.get('code'), current_user().get('username'))
    flash(msg, 'ok' if ok else 'warn')
    return redirect(request.referrer or url_for('admin.dashboard'))


@staff_required
def bookings():
    """预约管理：按状态/日期筛，能代客户取消、能核销"""
    rows = db.rows('bookings')
    status = request.args.get('status') or 'booked'      # 只用来点亮默认那颗筛选按钮
    kw = (request.args.get('q') or '').strip()
    # 状态筛选现在由前端就地做（tabs.js 藏行），所以这里不再过滤，全都渲染出来
    if kw:
        rows = [b for b in rows if kw in str(b.get('title', '')) or kw in str(b.get('username', ''))
                or kw in str(b.get('phone', '')) or kw in str(b.get('verifyCode', ''))]
    rows = sorted(rows, key=lambda x: (-(x.get('ts') or 0), str(x.get('time'))))
    return render_template('admin/panel_bookings.html', rows=rows, status=status, q=kw,
                           counts={s: len([b for b in db.rows('bookings') if b.get('status') == s])
                                   for s in ('booked', 'arrived', 'done', 'cancelled')})


@bp.post('/bookings/<int:bid>/cancel')
@staff_required
def cancel_booking(bid):
    """店里原因取消（退款按规则走 business.order_action）"""
    rows = db.rows('bookings')
    hit = next((b for b in rows if b.get('id') == bid), None)
    if not hit:
        flash('没这条预约', 'warn')
        return redirect(url_for('admin.dashboard') + '#bookings')
    hit.update(status='cancelled', cancelAt=business.now_ms(), cancelBy='staff')
    db.write('bookings', rows)
    order = next((o for o in db.rows('pays') if o.get('bid') == bid), None)
    if order:
        business.order_action(current_user(), order.get('id'), 'refund', is_staff=True)
    business.audit(current_user().get('username'), role(), '店员取消了《%s》%s 的预约'
                   % (hit.get('title'), hit.get('day')))
    flash('已取消并处理退款', 'ok')
    return redirect(url_for('admin.dashboard') + '#bookings')


@staff_required
def users():
    """用户档案：**所有人**都在这儿（普通用户 / DM / 管理员），
    点开一个人能改信用分、充值、拉黑、改角色。

    早先这里只列普通客户（role=='user'），员工在名单外，想改谁的角色得进数据库。
    现在全列出来，顶部可按角色筛。
    """
    kw = (request.args.get('q') or '').strip()
    role_filter = (request.args.get('role') or '').strip()
    me = current_user()
    bookings = db.rows('bookings')
    rows = []
    counts = {'user': 0, 'dm': 0, 'admin': 0, 'super': 0}
    for u in db.rows('users'):
        rs = business.roles_of(u)                 # 可能挂着好几个：既 DM 又管理员是很正常的
        r = business.role_of(u)                   # 主角色（卡片上那个徽章 / 排序用它）
        for x in rs:
            counts[x] = counts.get(x, 0) + 1      # 一人多角色就同时计入几个筛选，别漏
        if role_filter and role_filter not in rs:
            continue
        if kw and kw not in str(u.get('username')) and kw not in str(u.get('phone')):
            continue
        mine = [b for b in bookings if str(b.get('phone')) == str(u.get('phone')) and b.get('status') != 'cancelled']
        # 能不能改他的角色（跟 business.set_roles 的三条护栏保持一致，前端才好禁用）
        can_edit = (u.get('super') is not True and r != 'super'
                    and str(u.get('phone')) != str(me.get('phone'))
                    and ('admin' not in rs or 'super' in business.roles_of(me)))
        rows.append({'u': u, 'role': r, 'roles': rs,
                     'roleName': business.roles_text(rs),           # 完整（弹窗标题用）：普通用户、DM
                     'badge': business.roles_badge(rs),             # 短徽章：DM、管理员 / 普通用户
                     'roleNames': [business.ROLE_NAMES.get(x, x) for x in rs],
                     'canEditRole': can_edit,
                     'visits': len(mine), 'spent': sum(int(b.get('amount') or 0) for b in mine),
                     'last': max([b.get('createdAt') or 0 for b in mine] or [0]),
                     # 最近 3 次预约：点开用户档案时顺手给他看，不用再翻预约页
                     'recent': sorted(mine, key=lambda b: -(b.get('ts') or 0))[:3]})
    # 员工排前面（要改角色通常先找他们），同类里按来店次数
    rows.sort(key=lambda x: (-business.ROLE_RANK.get(x['role'], 0), -x['visits']))
    return render_template('admin/panel_users.html', rows=rows, q=kw,
                           role_filter=role_filter, counts=counts, me=me)


@bp.post('/users/<phone>/credit')
@staff_required
def set_credit(phone):
    delta = int(request.form.get('delta') or 0)
    reason = business.clean(request.form.get('reason'), 40) or '门店调整'
    before, after = business.adjust_credit(phone, delta, reason, current_user().get('username'))
    flash('信用分 %s → %s（原因：%s）' % (before, after, reason) if before is not None else '没这个账号',
          'ok' if before is not None else 'warn')
    return redirect(url_for('admin.dashboard') + '#users')


@bp.post('/users/<phone>/role')
@staff_required
def user_role(phone):
    """改角色：普通用户 / DM / 管理员 —— **可多选**（护栏都在 business.set_roles 里，这里只管跳回来）

    认两种交法：roles=[user,dm,admin]（新表单，多选）和 role=dm（老表单/老自检，单值）
    """
    roles = request.form.getlist('roles')
    if not roles and request.form.get('role'):
        roles = [request.form.get('role')]
    ok, msg = business.set_roles(phone, roles, current_user())
    flash(msg, 'ok' if ok else 'warn')
    return redirect(url_for('admin.dashboard') + '#users')


@bp.post('/users/<phone>/ban')
@staff_required
def ban(phone):
    users_rows = db.rows('users')
    hit = next((u for u in users_rows if str(u.get('phone')) == str(phone)), None)
    if not hit:
        flash('没这个账号', 'warn')
    elif hit.get('super') is True:
        flash('超管不能拉黑（自己把自己关门外就麻烦了）', 'warn')
    else:
        banned = not hit.get('banned')
        hit['banned'] = banned
        hit['banReason'] = business.clean(request.form.get('reason'), 60) if banned else ''
        db.write('users', users_rows)
        business.audit(current_user().get('username'), role(),
                       ('拉黑' if banned else '恢复') + '了 ' + str(hit.get('username')))
        flash('已拉黑该账号' if banned else '已恢复该账号', 'ok')
    return redirect(url_for('admin.dashboard') + '#users')


@bp.post('/users/<phone>/recharge')
@staff_required
def recharge(phone):
    """会员充值（余额记在账号上，以后下单可以抵扣）"""
    amount = int(request.form.get('amount') or 0)
    rows = db.rows('users')
    hit = next((u for u in rows if str(u.get('phone')) == str(phone)), None)
    if not hit or not amount:
        flash('账号或金额不对', 'warn')
    else:
        before = int(hit.get('balance') or 0)
        hit['balance'] = before + amount
        logs = hit.get('walletLogs') or []
        logs.insert(0, {'at': business.now_ms(), 'delta': amount, 'by': current_user().get('username'),
                        'note': business.clean(request.form.get('note'), 40)})
        hit['walletLogs'] = logs[:50]
        db.write('users', rows)
        business.notify(phone, '会员余额变动 💳', '充值 ¥%d，当前余额 ¥%d' % (amount, hit['balance']), 'wallet')
        flash('充值成功：¥%d → ¥%d' % (before, hit['balance']), 'ok')
    return redirect(url_for('admin.dashboard') + '#users')


@bp.post('/coupon')
@staff_required
def coupon():
    """发券：默认发给"好久没来"的客人（sleepDays 天没消费），也可以选全员或指定用户"""
    scope = request.form.get('scope') or 'sleeping'
    amount = int(request.form.get('amount') or 20)
    days = int(request.form.get('days') or 30)
    sleep_days = int(request.form.get('sleepDays') or 30)
    bookings = db.rows('bookings')
    users = db.rows('users')
    picked = []

    if scope == 'specific':
        target = (request.form.get('target') or '').strip()
        if not target:
            flash('指定用户需要填用户名或手机号', 'warn')
            return redirect(url_for('admin.dashboard'))
        u = next((x for x in users
                  if str(x.get('username')) == target or str(x.get('phone')) == target), None)
        if not u:
            flash('没找到这个用户（按用户名或手机号）', 'warn')
            return redirect(url_for('admin.dashboard'))
        picked.append(u)
    else:
        cut = business.now_ms() - sleep_days * 86400000
        for u in users:
            if not business.has_role(u, 'dm', 'admin'):   # 多角色：员工（DM/管理员）不算普通用户
                continue
            if scope == 'all':
                picked.append(u)
                continue
            last = max([b.get('createdAt') or 0 for b in bookings if str(b.get('phone')) == str(u.get('phone'))]
                       or [u.get('first') or 0])
            if last < cut:
                picked.append(u)

    for u in picked:
        db.update('coupons', lambda rows: rows + [{
            'id': business.now_ms() + len(picked), 'phone': u.get('phone'), 'amount': amount,
            'minAmount': 0, 'used': False, 'from': '门店回访',
            'exp': business.now_ms() + days * 86400000}])
        business.notify(u.get('phone'), '送你一张券 🎁',
                        '送你 %d 元游玩费抵扣券（%d 天内有效）' % (amount, days), 'coupon')
    flash('发出 %d 张券' % len(picked) if picked else '没有符合条件的客人', 'ok' if picked else 'warn')
    return redirect(url_for('admin.dashboard'))


@staff_required
def scripts():
    """剧本管理：改价、上下架、角色、是否允许客人提前选角"""
    return render_template('admin/panel_scripts.html', rows=db.rows('scripts'),
                           tag_presets=TAG_PRESETS)


@bp.post('/scripts/new')
@staff_required
def script_new():
    """加一个新剧本：页面上填个名字就能建，细节建完再改（列表最下面那个）"""
    rows = db.rows('scripts')
    new_id = max([int(s.get('id') or 0) for s in rows] or [0]) + 1
    rows.append({'id': new_id, 'title': business.clean(request.form.get('title'), 30) or '新剧本',
                 'emoji': business.clean(request.form.get('emoji'), 4) or '🎭', 'tags': [],
                 'players': '6人', 'dur': '约4小时', 'diff': 3,
                 'price': int(request.form.get('price') or 128), 'desc': '',
                 'type': '盒装', 'stock': '在库', 'onSale': True, 'allowRolePick': False,
                 'roles': [], 'dms': [], 'hot': False, 'isNew': True, 'createdAt': business.now_ms()})
    db.write('scripts', rows)
    business.audit(current_user().get('username'), role(), '新增剧本《%s》' % rows[-1]['title'])
    flash('《%s》建好了，下面填细节' % rows[-1]['title'], 'ok')
    return redirect(url_for('admin.dashboard') + '#scripts')


@bp.get('/scripts/export')
@staff_required
def scripts_export():
    """导出剧本库成 CSV —— Excel 能直接打开，改完再导回来"""
    import csv
    import io

    from flask import Response
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['id', 'title', 'emoji', 'tags', 'players', 'dur', 'diff', 'price', 'type',
                'onSale', 'allowRolePick', 'roles', 'desc'])
    for s in db.rows('scripts'):
        w.writerow([s.get('id'), s.get('title'), s.get('emoji'), '/'.join(s.get('tags') or []),
                    s.get('players'), s.get('dur'), s.get('diff'), s.get('price'), s.get('type'),
                    1 if s.get('onSale') is not False else 0,
                    1 if s.get('allowRolePick') else 0,
                    ','.join(r.get('name') for r in (s.get('roles') or [])), s.get('desc')])
    data = '\ufeff' + buf.getvalue()          # 前面这个 BOM 是给 Excel 看的，不然中文乱码
    return Response(data, mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename=scripts.csv'})


@bp.post('/scripts/import')
@staff_required
def scripts_import():
    """导入 CSV：填了 id 就更新那条，id 空着就当新本加进来

    一次录 20 个本不用一个个建；tags 用 / 或 , 分隔，roles 用逗号分隔。
    """
    import csv
    import io

    f = request.files.get('csv')
    if not f or not f.filename:
        flash('先选一个 CSV 文件（可以先用「导出」下一个当模板）', 'warn')
        return redirect(url_for('admin.dashboard') + '#scripts')
    text = f.read().decode('utf-8-sig', 'replace')
    rows = db.rows('scripts')
    by_id = {str(s.get('id')): s for s in rows}
    next_id = max([int(s.get('id') or 0) for s in rows] or [0]) + 1
    added = updated = skipped = 0
    for raw in csv.DictReader(io.StringIO(text)):
        title = (raw.get('title') or '').strip()
        if not title:
            skipped += 1
            continue
        sid = (raw.get('id') or '').strip()
        rec = by_id.get(sid) if sid else None
        tags_raw = (raw.get('tags') or '').replace('，', '/').replace(',', '/')
        item = {
            'title': title, 'emoji': (raw.get('emoji') or '🎭').strip(),
            'tags': [t.strip() for t in tags_raw.split('/') if t.strip()],
            'players': (raw.get('players') or '6人').strip(),
            'dur': (raw.get('dur') or '约4小时').strip(),
            'diff': int(raw['diff']) if str(raw.get('diff') or '').strip().isdigit() else 3,
            'price': int(float(raw.get('price') or 128)),
            'type': (raw.get('type') or '盒装').strip(),
            'onSale': str(raw.get('onSale') or '1').strip() not in ('0', '否', 'false', 'False'),
            'allowRolePick': str(raw.get('allowRolePick') or '0').strip() in ('1', '是', 'true', 'True'),
            'roles': [{'name': n.strip(), 'img': ''} for n in (raw.get('roles') or '').replace('，', ',').split(',')
                      if n.strip()],
            'desc': (raw.get('desc') or '').strip(),
        }
        if rec:
            rec.update(item)
            updated += 1
        else:
            item['id'] = next_id
            next_id += 1
            rows.append(item)
            added += 1
    db.write('scripts', rows)
    business.audit(current_user().get('username'), role(),
                   '导入剧本 CSV：新增 %d、更新 %d' % (added, updated))
    flash('导入完成：新增 %d 个、更新 %d 个%s'
          % (added, updated, ('、跳过 %d 行（没填名字）' % skipped) if skipped else ''), 'ok')
    return redirect(url_for('admin.dashboard') + '#scripts')


@bp.post('/scripts/<int:sid>/img')
@staff_required
def script_img(sid):
    """传剧本封面（建议 4:3，压到 300KB 以内，打开快）"""
    rows = db.rows('scripts')
    hit = next((s for s in rows if s.get('id') == sid), None)
    if not hit:
        flash('没这个剧本', 'warn')
        return redirect(url_for('admin.dashboard') + '#scripts')
    url, err = business.save_upload(request.files.get('cover'), 'cover')
    if not url:
        flash('封面没传上：%s' % err, 'warn')
    else:
        hit['img'] = url
        db.write('scripts', rows)
        business.audit(current_user().get('username'), role(), '换了《%s》的封面' % hit.get('title'))
        flash('封面换好了（前台立刻能看到）', 'ok')
    return redirect(url_for('admin.dashboard') + '#scripts')


@bp.post('/scripts/<int:sid>/role-img')
@staff_required
def script_role_img(sid):
    """给角色传头像图 / 删图（按 roles 列表里的**下标**定位）。

    现在支持两种提交方式：
      1. 单格旧表单：name="img" + idx=下标（删图也走这里）。
      2. 批量新表单：每个角色一个 input，name="img_0", "img_1"... 一起上传。

    为什么用下标不用角色名：名字随时可能改，图得跟着那一格走 ——
    用名字配对的话，改个名图就串到别人头上。表单里带 remove=1 就是删图。
    """
    rows = db.rows('scripts')
    hit = next((s for s in rows if s.get('id') == sid), None)
    if not hit:
        flash('没这个剧本', 'warn')
        return redirect(url_for('admin.dashboard') + '#scripts')
    roles = hit.get('roles') or []

    # ① 删图或单图上传（兼容旧入口）
    try:
        idx = int(request.form.get('idx') or -1)
    except ValueError:
        idx = -1
    if request.form.get('remove'):
        if idx < 0 or idx >= len(roles):
            flash('角色对不上（可能刚改过角色名，刷新页面再传一次）', 'warn')
            return redirect(url_for('admin.dashboard') + '#scripts')
        who = roles[idx].get('name')
        roles[idx]['img'] = ''
        flash('「%s」的图删了' % who, 'ok')
        hit['roles'] = roles
        db.write('scripts', rows)
        return redirect(url_for('admin.dashboard') + '#scripts')

    single = request.files.get('img')
    if single:
        if idx < 0 or idx >= len(roles):
            flash('角色对不上（可能刚改过角色名，刷新页面再传一次）', 'warn')
            return redirect(url_for('admin.dashboard') + '#scripts')
        url, err = business.save_upload(single, 'role')
        if not url:
            flash('图没传上：%s' % err, 'warn')
            return redirect(url_for('admin.dashboard') + '#scripts')
        roles[idx]['img'] = url
        flash('「%s」的图换好了（前台立刻能看到）' % roles[idx].get('name'), 'ok')
        hit['roles'] = roles
        db.write('scripts', rows)
        return redirect(url_for('admin.dashboard') + '#scripts')

    # ② 批量上传：img_0, img_1, ...
    updated = []
    for key in sorted(request.files.keys()):
        if not key.startswith('img_'):
            continue
        try:
            idx = int(key.split('_', 1)[1])
        except (ValueError, IndexError):
            continue
        if idx < 0 or idx >= len(roles):
            continue
        f = request.files[key]
        if not f or not f.filename:
            continue
        url, err = business.save_upload(f, 'role')
        if not url:
            flash('「%s」的图没传上：%s' % (roles[idx].get('name'), err), 'warn')
            continue
        roles[idx]['img'] = url
        updated.append(roles[idx].get('name'))
    if updated:
        flash('已上传 %d 个角色图：%s' % (len(updated), '、'.join(updated)), 'ok')
    else:
        flash('没有选中的角色图片需要上传', 'warn')
    hit['roles'] = roles
    db.write('scripts', rows)
    return redirect(url_for('admin.dashboard') + '#scripts')


@bp.post('/scripts/<int:sid>/save')
@staff_required
def script_save(sid):
    rows = db.rows('scripts')
    hit = next((s for s in rows if s.get('id') == sid), None)
    if not hit:
        flash('没这个剧本', 'warn')
        return redirect(url_for('admin.dashboard') + '#scripts')
    f = request.form
    if f.get('title'):
        hit['title'] = business.clean(f.get('title'), 30)
    if f.get('price'):
        hit['price'] = int(f.get('price'))
    hit['onSale'] = f.get('onSale') == '1'
    hit['allowRolePick'] = f.get('allowRolePick') == '1'      # 开了客人才能在网页上选角色
    if f.get('players'):
        hit['players'] = business.clean(f.get('players'), 12)
    if f.get('dur') is not None:
        hit['dur'] = business.clean(f.get('dur'), 12)          # 时长：例"约4小时"
    if f.get('type') is not None:
        hit['type'] = business.clean(f.get('type'), 12)        # 类型：盒装/独家/情感…
    if f.get('diff'):
        try:
            hit['diff'] = max(1, min(5, int(f.get('diff'))))   # 难度：钳在 1-5，别让人填 99
        except ValueError:
            pass
    if f.get('tags') is not None:
        hit['tags'] = [x.strip() for x in str(f.get('tags')).replace('，', ',').split(',')
                       if x.strip()][:8]                # 标签：最多 8 个，多了前台也摆不下
    if f.get('desc') is not None:
        hit['desc'] = business.clean(f.get('desc'), 200)
    if f.get('roles') is not None:
        names = [x.strip() for x in str(f.get('roles')).replace('，', ',').split(',') if x.strip()]
        old = {r.get('name'): r for r in hit.get('roles') or []}
        hit['roles'] = [old.get(n, {'name': n, 'img': ''}) for n in names]
    db.write('scripts', rows)
    business.audit(current_user().get('username'), role(), '改了剧本《%s》' % hit.get('title'))
    flash('《%s》存好了' % hit.get('title'), 'ok')
    return redirect(url_for('admin.dashboard') + '#scripts')


@staff_required
def orders():
    """订单 + 日结：一天卖了多少、退了多少"""
    rows = sorted(db.rows('pays'), key=lambda x: -(x.get('id') or 0))
    status = request.args.get('status') or 'all'         # 状态筛选在前端做，不在这儿过滤
    by_day = {}
    for o in db.rows('pays'):
        if o.get('status') == 'paid':
            d = o.get('day') or '未知'
            by_day[d] = by_day.get(d, 0) + int(o.get('deposit') or 0)
    return render_template('admin/panel_orders.html', rows=rows, status=status,
                           by_day=sorted(by_day.items(), key=lambda kv: kv[0], reverse=True)[:14])


@staff_required
def growth():
    """DM 成长档案：每个 DM 的账号、段位、擅长本、带本情况、客人反馈、这个月能拿多少

    DM 自己在工作台里看到的是自己那一份；这里是给店里看的全局视图 ——
    谁在成长、谁该多排场、谁的反馈需要聊一聊，一屏看完。
    """
    month = request.args.get('month') or __import__('time').strftime('%Y-%m')
    settle = {r['dmPhone']: r for r in business.dm_settlement(month)['rows']}
    reviews = [r for r in db.rows('reviews') if not r.get('hidden')]
    scripts = {str(s.get('id')): s for s in db.rows('scripts')}
    sessions, bookings = db.rows('sessions'), db.rows('bookings')
    rows = []
    for u in db.rows('users'):
        if not business.has_role(u, 'dm'):           # 挂着 dm 就算（同时是管理员也算）
            continue
        phone = str(u.get('phone'))
        g = business.dm_growth(phone)
        my_ses = {s.get('id') for s in sessions if str(s.get('dm')) == phone}
        cnt = {}
        for b in bookings:
            if b.get('status') == 'cancelled':
                continue
            if b.get('sessionId') in my_ses or str(b.get('dmPhone')) == phone:
                cnt[str(b.get('sid'))] = cnt.get(str(b.get('sid')), 0) + 1
        rows.append({
            'u': u, 'phone': phone, 'g': g, 'mon': settle.get(phone) or {},
            'nick': (u.get('profile') or {}).get('nick') or u.get('username'),
            # 擅长本 = 他带得最多的三个本
            'best': [{'title': (scripts.get(k) or {}).get('title') or '（已下架）', 'n': n}
                     for k, n in sorted(cnt.items(), key=lambda kv: -kv[1])[:3]],
            # 客人反馈 = 点名给他的那些评价，最近的在前
            'fb': sorted([r for r in reviews if str(r.get('dmPhone')) == phone],
                         key=lambda r: -(r.get('createdAt') or 0))[:3],
        })
    rows.sort(key=lambda x: (-x['g']['done'], -x['g']['rating']))
    return render_template('admin/panel_growth.html', rows=rows, month=month,
                           tiers=business.DM_TIERS, dm_count=len(rows))


@bp.post('/orders/<int:oid>/confirm')
@dm_required
def order_confirm(oid):
    """确认收款（客人在支付页点完「我已完成支付」之后，由店里确认）

    定金 / 尾款共用这一颗按钮：按订单当前状态自动挑动作。
    DM 也能点（带完本当场收尾款最方便）—— 所以闸门是 dm_required，不是 staff_required。
    """
    o = next((x for x in db.rows('pays') if str(x.get('id')) == str(oid)), None)
    action = 'pay-bal' if (o or {}).get('balStatus') == 'claimed' else 'pay'
    ok, msg = business.order_action(current_user(), oid, action, is_staff=True)
    flash(msg, 'ok' if ok else 'warn')
    return redirect(url_for('admin.dashboard') + '#orders')


@bp.post('/orders/<int:oid>/forfeit')
@staff_required
def order_forfeit(oid):
    """标记未到 / 中途跳车：定金按门店规矩不退（这笔钱门店收了）。

    一键做完三件事：单子关掉、位子放回池子（人没来的话）、通知客人 + 留操作日志。
    只给门店点（staff_required）—— 钱的事不让 DM 或客人自己操作。
    """
    ok, msg = business.order_action(current_user(), oid, 'forfeit', is_staff=True,
                                    reason=(request.form.get('reason') or '').strip())
    flash(msg, 'ok' if ok else 'warn')
    return redirect(url_for('admin.dashboard') + '#orders')


@bp.post('/mail/test')
@staff_required
def mail_test():
    """发一封测试邮件 —— 验证码发信的配置对不对，点一下就知道（不用真去注册个号）"""
    to = (request.form.get('to') or '').strip() or str(current_user().get('email') or '')
    if not to:
        flash('先填一个收件邮箱', 'warn')
    else:
        st = business.get_settings()
        ok, err = business.send_mail(to, '【%s】发信测试' % (st.get('shopName') or '甜薯剧本杀'),
                                     '这是一封测试邮件。\n收到它，说明客人注册/找回密码的验证码也能正常发出。\n',
                                     st)
        flash('测试邮件已发出 → %s（没看到就翻翻垃圾邮件箱）' % to if ok else '没发出去：%s' % err,
              'ok' if ok else 'warn')
        business.audit(current_user().get('username'), role(), '点了发信测试（%s）' % ('成功' if ok else '失败'))
    return redirect(url_for('admin.dashboard'))


@bp.post('/settings/group-qr')
@staff_required
def settings_group_qr():
    """门店群二维码：传一张图，客人「支付定金 / 游玩费」那一页就会显示它。

    单独一个路由（不是塞进 /settings）：HTML 里表单不能嵌套，而且这里要收文件。
    """
    rows = db.read('settings') or {}
    if request.form.get('remove'):
        rows['groupQr'] = ''
        db.write('settings', rows)
        business.audit(current_user().get('username'), role(), '删掉了门店群二维码')
        flash('群二维码删掉了（支付页不再显示）', 'ok')
        return redirect(url_for('admin.dashboard') + '#dash')
    url, err = business.save_upload(request.files.get('qr'), 'qr')
    if not url:
        flash('二维码没传上：%s' % err, 'warn')
    else:
        rows['groupQr'] = url
        db.write('settings', rows)
        business.audit(current_user().get('username'), role(), '换了门店群二维码')
        flash('群二维码换好了（客人的支付页立刻能看到）', 'ok')
    return redirect(url_for('admin.dashboard') + '#dash')


@bp.post('/settings/shop-photos')
@staff_required
def settings_shop_photos():
    """店铺实拍墙：传几张真实照片（前台 / 房间 / 道具…），首页照片墙会显示。

    表单里可带多张文件（name=photo），每张配一句说明（name=cap）；
    也可只删某一张（带 rid 参数 = 那张的 url）。HTML 表单不能嵌套，单独成路由。
    """
    rows = db.read('settings') or {}
    photos = list(rows.get('shopPhotos') or [])
    rid = request.form.get('rid')
    if rid:                       # 删一张
        rows['shopPhotos'] = [p for p in photos if p.get('url') != rid]
        db.write('settings', rows)
        business.audit(current_user().get('username'), role(), '删了张店铺实拍')
        flash('删掉了', 'ok')
        return redirect(url_for('admin.dashboard') + '#dash')
    caps = request.form.getlist('cap')
    for i, fs in enumerate(request.files.getlist('photo')):
        url, err = business.save_upload(fs, 'shop')
        if url:
            photos.append({'url': url, 'cap': (caps[i] if i < len(caps) else '') or ''})
        elif err and fs and fs.filename:
            flash('有张图没存上：%s' % err, 'warn')
    rows['shopPhotos'] = photos
    if request.form.get('intro') is not None:
        rows['shopIntro'] = business.clean(request.form.get('intro'), 120)
    db.write('settings', rows)
    business.audit(current_user().get('username'), role(), '更新了店铺实拍（%d 张）' % len(photos))
    flash('店铺实拍存好了，首页照片墙立刻能看到', 'ok')
    return redirect(url_for('admin.dashboard') + '#dash')


@bp.post('/settings')
@staff_required
def settings():
    """经营参数：改完立刻生效（存在 data/settings.json，也可以直接改那个文件）"""
    rows = db.read('settings') or {}
    f = request.form
    for k in ('shopName', 'notice'):
        if f.get(k) is not None:
            rows[k] = business.clean(f.get(k), 80)
    # 小客服微信号：客人点「支付定金」那页上显示的就是它
    if f.get('serviceWechat') is not None:
        rows['serviceWechat'] = business.clean(f.get('serviceWechat'), 40)
    # 验证码发信：先定通道，再存各通道的凭据
    if f.get('mailProvider') in ('', 'resend', 'smtp', 'webhook'):
        rows['mailProvider'] = f.get('mailProvider')
    for k in ('mailFrom', 'mailSubject', 'mailWebhook'):
        if f.get(k) is not None:
            rows[k] = business.clean(f.get(k), 120)
    if f.get('mailKey') is not None:
        _k = business.clean(f.get('mailKey'), 120)
        # 表单里放的是打码值（••••••••xxxx）：原样交回来 = 没改，别把真 Key 冲掉
        if _k and '•' not in _k:
            rows['mailKey'] = _k
    # 发件人昵称：客人收件箱里显示的名字（留空 = 只显示地址），见 business.mail_from_name
    if f.get('mailFromName') is not None:
        rows['mailFromName'] = business.clean(f.get('mailFromName'), 40)
    # 外观款式：手机端 / 电脑端分开选（都只认白名单里的值 —— 会被拼进 CSS 文件名，
    # 不校验等于让人指定任意静态文件，路径穿越老套路，必须卡死）。两者都留空就回退到 skin。
    if f.get('skin_desktop') in business.SKINS:
        rows['skin_desktop'] = f.get('skin_desktop')
    if f.get('skin_mobile') in business.SKINS:
        rows['skin_mobile'] = f.get('skin_mobile')
    # 历史兼容：单款式旧值（二选一都没配时回退用）
    if f.get('skin') in business.SKINS:
        rows['skin'] = f.get('skin')
    # 网站版式（一代 / 二代）：决定客人看到的那套模板和样式表。同样只认白名单 ——
    # 它会决定加载哪一套 CSS、走哪个模板目录，不能让人随便填。
    if f.get('uiVer') in business.UI_VERSIONS:
        rows['uiVer'] = f.get('uiVer')
    for k in ('smtpHost', 'smtpUser', 'smtpFrom'):
        if f.get(k) is not None:
            rows[k] = business.clean(f.get(k), 80)
    if f.get('smtpPass') is not None:
        rows['smtpPass'] = business.clean(f.get('smtpPass'), 120)
    if f.get('smtpPort'):
        try:
            rows['smtpPort'] = int(float(f.get('smtpPort')))
        except ValueError:
            pass
    if f.get('dmPayMode') in ('rate', 'fixed'):
        rows['dmPayMode'] = f.get('dmPayMode')
    for k in ('dmFee', 'depositRatio', 'freeCancelHours', 'lateCancelPenalty', 'dmRate', 'dmFixedPay',
              'carDeposit', 'inviteCoupon'):
        if f.get(k):
            try:
                rows[k] = float(f.get(k))
            except ValueError:
                pass
    rows['carTags'] = [t.strip() for t in (f.get('carTags') or '').replace('，', ',').split(',') if t.strip()][:6] \
        if f.get('carTags') is not None else rows.get('carTags', [])
    if f.get('banners') is not None:              # 首页轮播，一行一条
        rows['banners'] = business.parse_banners(f.get('banners'))
    db.write('settings', rows)
    business.audit(current_user().get('username'), role(), '改了门店设置')
    flash('设置已保存（立刻生效）', 'ok')
    return redirect(url_for('admin.dashboard'))


@staff_required
def logs():
    return render_template('admin/panel_logs.html', rows=db.rows('logs')[:200])


# ---------------------------------------------------------------- 排期（每天真正要用的）
@staff_required
def sessions():
    """一天的排期：新排一场、锁场、取消；同一房间同一时段排两场会被拦下来"""
    try:
        ts = int(request.args.get('ts') or business.midnight())
    except ValueError:
        ts = business.midnight()
    dms = [u for u in db.rows('users') if business.has_role(u, 'dm')]
    view = request.args.get('view') or 'day'
    week = []
    if view == 'week':                       # 周视图：一眼看整周，撞没撞房立刻看出来
        import time as _t
        wd = _t.localtime(ts / 1000).tm_wday                 # 0 = 周一
        monday = ts - wd * 86400000
        for i in range(7):
            d = monday + i * 86400000
            week.append({'ts': d, 'day': business.day_label(d), 'rows': business.sessions_of(d)})
    rows = business.sessions_of(ts)
    # 「全部房间」总览：把这一天的场次按房间归堆 —— 一眼看出哪间空着、哪间排满了
    room_map = {}
    for s in rows:
        room_map.setdefault(s.get('roomId') or '房间待定', []).append(s)
    # 待安排：客人已经下单、但还没给房间和 DM 的预约 —— 时间客人定了，这里只挑房和 DM
    pending = [b for b in db.rows('bookings')
               if b.get('status') == 'booked' and not b.get('sessionId')
               and (b.get('ts') or 0) >= business.midnight()]
    pending.sort(key=lambda x: (x.get('ts') or 0, str(x.get('time'))))
    for b in pending:
        b['dayTxt'] = business.day_label(b.get('ts') or 0)
    return render_template('admin/panel_sessions.html', rows=rows, ts=ts, view=view,
                           prev=ts - 86400000, nxt=ts + 86400000, day=business.day_label(ts),
                           week=week, rooms=db.rows('rooms'), dms=dms, room_map=room_map,
                           times=SESSION_TIMES, pending=pending)


@bp.post('/bookings/<int:bid>/arrange')
@staff_required
def booking_arrange(bid):
    """把一条预约安排进房间：**时间客人已经定了**，这里只挑房间和 DM。

    同剧本同时段已经有场（比如拼车的另一拨）就并进去，没有就新开一场；
    一个房间一个时段只演一场，冲突会被拦下来。安排完客人和 DM 都会收到通知。
    """
    bookings = db.rows('bookings')
    hit = next((b for b in bookings if str(b.get('id')) == str(bid)), None)
    if not hit:
        flash('没这条预约', 'warn')
        return redirect(url_for('admin.dashboard') + '#sessions')
    if hit.get('status') != 'booked':
        flash('这条预约已经取消 / 玩完了，安排不了', 'warn')
        return redirect(url_for('admin.dashboard') + '#sessions')
    room = business.clean(request.form.get('roomId'), 20)
    dm = business.clean(request.form.get('dm'), 20)
    ts, tm = hit.get('ts') or 0, hit.get('time') or '19:00'
    # 已经安排过（多半是又点了一次）：当成"改安排 / 补房间补 DM"，不再甩一句失败
    redo = bool(hit.get('sessionId'))
    if redo and not room and not dm:
        _ses = next((s for s in db.rows('sessions') if s.get('id') == hit.get('sessionId')), {})
        flash('这条已经安排过了（房间 %s · DM %s）。要改就选好房间或 DM 再点一次。'
              % (_ses.get('roomId') or '待定', _ses.get('dm') or '待定'), 'info')
        return redirect(url_for('admin.dashboard', ts=ts, view='day') + '#sessions')

    sessions = db.rows('sessions')
    ses = next((s for s in sessions if str(s.get('sid')) == str(hit.get('sid'))
                and s.get('ts') == ts and s.get('time') == tm and s.get('status') == 'open'), None)
    if ses:
        used = sum(int(b.get('players') or 0) for b in bookings
                   if b.get('sessionId') == ses.get('id') and b.get('status') != 'cancelled')
        if room and (ses.get('roomId') or '') != room and business.room_busy(room, ts, tm):
            flash('%s 在 %s 已经有别的场了 —— 换一间房' % (room, tm), 'warn')
            return redirect(url_for('admin.dashboard', ts=ts, view='day') + '#sessions')
        if room:
            ses['roomId'] = room
        if dm:
            ses['dm'] = dm
        ses['cap'] = max(int(ses.get('cap') or 0), used) + int(hit.get('players') or 0)
    else:
        if room and business.room_busy(room, ts, tm):
            flash('%s 在 %s 已经有别的场了 —— 换一间房' % (room, tm), 'warn')
            return redirect(url_for('admin.dashboard', ts=ts, view='day') + '#sessions')
        room_row = next((r for r in db.rows('rooms') if r.get('name') == room), {})
        ses = {'id': business.now_ms() + secrets.randbelow(90), 'sid': hit.get('sid'),
               'title': hit.get('title'), 'ts': ts, 'time': tm, 'roomId': room or '',
               'dm': dm, 'cap': int(room_row.get('cap') or hit.get('players') or 6),
               'status': 'open', 'createdAt': business.now_ms()}
        sessions.append(ses)
    hit['sessionId'] = ses['id']
    db.write('sessions', sessions)
    db.write('bookings', bookings)
    dm_row = next((u for u in db.rows('users') if str(u.get('phone')) == str(dm)), {})
    business.notify(hit.get('phone'), '你的场次有更新 🔁' if redo else '已为你安排房间 ✅',
                    '《%s》%s %s 安排在 %s，DM：%s —— 到店报核销码就行。'
                    % (hit.get('title'), hit.get('day'), tm, room or '房间待定',
                       (dm_row.get('profile') or {}).get('nick') or dm_row.get('username') or '待定'), 'arrange')
    if dm:
        business.notify(dm, '新场次',
                        '《%s》%s %s 在 %s，你来带（%d 人）。'
                        % (hit.get('title'), hit.get('day'), tm, room or '房间待定',
                           int(hit.get('players') or 0)), 'sched')
    business.audit(current_user().get('username'), role(), '安排《%s》%s %s → %s · DM %s'
                   % (hit.get('title'), hit.get('day'), tm, room or '待定', dm or '待定'))
    flash('%s：%s · %s · DM %s'
          % ('已更新安排' if redo else '安排好了', tm, room or '待定', dm or '待定'), 'ok')
    return redirect(url_for('admin.dashboard', ts=ts, view='day') + '#sessions')


@bp.post('/sessions/new')
@staff_required
def session_new():
    f = request.form
    ts = int(f.get('ts') or business.midnight())
    tm = str(f.get('time') or '19:00')
    room = business.clean(f.get('roomId'), 20)
    busy = business.room_busy(room, ts, tm)
    if busy:
        flash('撞房了：%s %s 的「%s」已经排了《%s》，换个房间或时间'
              % (business.day_label(ts), tm, room, busy.get('title')), 'warn')
        return redirect(url_for('admin.dashboard') + '#sessions')
    sc = db.one('scripts', id=f.get('sid'))
    dm_phone = business.clean(f.get('dm'), 20)
    dm = db.one('users', phone=dm_phone) if dm_phone else None
    rows = db.rows('sessions')
    rows.append({'id': max([int(x.get('id') or 0) for x in rows] or [0]) + 1,
                 'sid': (sc or {}).get('id'), 'title': (sc or {}).get('title') or '临时场',
                 'ts': ts, 'time': tm, 'roomId': room, 'cap': int(f.get('cap') or 6),
                 'dm': dm_phone, 'dmName': (dm or {}).get('username') or '',
                 'status': 'open', 'createdAt': business.now_ms()})
    db.write('sessions', rows)
    business.audit(current_user().get('username'), role(),
                   '排期：%s %s《%s》%s' % (business.day_label(ts), tm, rows[-1]['title'], room))
    flash('排好了：%s %s《%s》' % (business.day_label(ts), tm, rows[-1]['title']), 'ok')
    return redirect(url_for('admin.dashboard') + '#sessions')


@bp.post('/sessions/<int:sid>/status')
@staff_required
def session_status(sid):
    """改一场的状态：开放 / 锁场 / 取消 / 完成。取消会通知已报名的客人"""
    rows = db.rows('sessions')
    hit = next((s for s in rows if s.get('id') == sid), None)
    if not hit:
        flash('没这场', 'warn')
        return redirect(url_for('admin.dashboard') + '#sessions')
    st = request.form.get('status') or 'open'
    if st == 'open':
        busy = business.room_busy(hit.get('roomId'), hit.get('ts'), hit.get('time'), skip_id=sid)
        if busy:
            flash('这间房那个时段已经排了《%s》，没法恢复开放' % busy.get('title'), 'warn')
            return redirect(url_for('admin.dashboard') + '#sessions')
    hit['status'] = st
    if request.form.get('reason'):
        hit['statusReason'] = business.clean(request.form.get('reason'), 60)
    db.write('sessions', rows)
    if st == 'cancelled':
        for b in db.rows('bookings'):
            if b.get('sessionId') == sid and b.get('status') == 'booked':
                business.notify(b.get('phone'), '场次变动',
                                '《%s》%s %s 这场被取消了（%s），想换时间跟我们说'
                                % (hit.get('title'), business.day_label(hit.get('ts')), hit.get('time'),
                                   hit.get('statusReason') or '门店原因'), 'session')
    business.audit(current_user().get('username'), role(),
                   '场次《%s》%s %s → %s' % (hit.get('title'), business.day_label(hit.get('ts')), hit.get('time'), st))
    flash('状态改成：%s' % st, 'ok')
    return redirect(url_for('admin.dashboard') + '#sessions')


@bp.post('/rooms/new')
@staff_required
def room_new():
    name = business.clean(request.form.get('name'), 20)
    if not name:
        flash('房间要有名字', 'warn')
    else:
        rows = db.rows('rooms')
        rows.append({'id': max([int(x.get('id') or 0) for x in rows] or [0]) + 1, 'name': name,
                     'cap': int(request.form.get('cap') or 6), 'dev': business.clean(request.form.get('dev'), 40)})
        db.write('rooms', rows)
        flash('加了房间：%s' % name, 'ok')
    return redirect(url_for('admin.dashboard') + '#sessions')


@bp.post('/rooms/<int:rid>/del')
@staff_required
def room_del(rid):
    db.write('rooms', [r for r in db.rows('rooms') if r.get('id') != rid])
    flash('房间删了（已排的场次不受影响，但那些场次会显示空房间）', 'ok')
    return redirect(url_for('admin.dashboard') + '#sessions')


# ---------------------------------------------------------------- 评价
@staff_required
def reviews():
    return render_template('admin/panel_reviews.html', rows=business.reviews_of(only_visible=False))


@bp.post('/reviews/<int:rid>/reply')
@staff_required
def review_reply(rid):
    """门店回复：客人会收到通知（差评好好回，别删）"""
    text = business.clean(request.form.get('text'), 300)
    rows = db.rows('reviews')
    hit = next((r for r in rows if r.get('id') == rid), None)
    if not hit:
        flash('没这条评价', 'warn')
    else:
        hit['reply'] = text
        hit['repliedBy'] = current_user().get('username')
        hit['repliedAt'] = business.now_ms()
        db.write('reviews', rows)
        bk = next((b for b in db.rows('bookings') if b.get('id') == hit.get('bid')), None)
        if bk:
            business.notify(bk.get('phone'), '门店回复了你的评价',
                            '《%s》那条评价，店家说：%s' % (bk.get('title'), text), 'review')
        flash('回复已发出', 'ok')
    return redirect(url_for('admin.dashboard') + '#reviews')


@bp.post('/reviews/<int:rid>/hide')
@staff_required
def review_hide(rid):
    rows = db.rows('reviews')
    for r in rows:
        if r.get('id') == rid:
            r['hidden'] = not r.get('hidden')
    db.write('reviews', rows)
    flash('已切换显示状态（隐藏的只有员工看得见）', 'ok')
    return redirect(url_for('admin.dashboard') + '#reviews')


# ---------------------------------------------------------------- 学本资料库 + 练本
@staff_required
def guides_page():
    """DM 的学本资料（解析/话术/复盘）+ 练本申请，都在这儿管"""
    return render_template('admin/panel_guides.html', guides=business.guides(),
                           practices=business.practices(), scripts=db.rows('scripts'))


@bp.post('/guides/new')
@staff_required
def guide_new():
    f = request.form
    links = []
    for line in (f.get('links') or '').splitlines():          # 一行一个：名字|网址
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 2 and parts[1].startswith(('http://', 'https://')):
            links.append({'name': parts[0] or '参考资料', 'url': parts[1]})
    db.update('guides', lambda rows: rows + [{
        'id': business.now_ms(), 'sid': int(f.get('sid') or 0), 'type': f.get('type') or '解析',
        'title': business.clean(f.get('title'), 60) or '未命名资料',
        'text': business.clean(f.get('text'), 5000), 'links': links[:8],
        'by': current_user().get('username'), 'at': business.now_ms()}])
    business.audit(current_user().get('username'), role(), '上传了学本资料')
    flash('资料发布了，DM 端立刻能看到', 'ok')
    return redirect(url_for('admin.dashboard') + '#guides')


@bp.post('/guides/<int:gid>/del')
@staff_required
def guide_del(gid):
    db.write('guides', [g for g in db.rows('guides') if g.get('id') != gid])
    flash('资料删了', 'ok')
    return redirect(url_for('admin.dashboard') + '#guides')


@bp.post('/practices/<int:pid>/status')
@staff_required
def practice_status(pid):
    """处理练本申请：安排 / 完成 / 婉拒（DM 会收到通知）"""
    st = request.form.get('status') or 'planned'
    rows = db.rows('practices')
    hit = next((p for p in rows if p.get('id') == pid), None)
    if hit:
        hit['status'] = st
        hit['handledBy'] = current_user().get('username')
        db.write('practices', rows)
        business.notify(hit.get('phone'), '练本申请有新进展',
                        '你申请的练本：%s' % {'planned': '门店已安排，等你时间确认',
                                             'done': '已练完，辛苦啦',
                                             'rejected': '这次先不安排，下次优先你'}.get(st, '已处理'), 'practice')
        flash('已处理', 'ok')
    return redirect(url_for('admin.dashboard') + '#guides')


# ---------------------------------------------------------------- 通知群发
@staff_required
def notice_page():
    """给客人/DM 群发站内消息（节日问候、临时停业、活动通知都用它）"""
    recent = [n for n in db.rows('notices') if n.get('kind') == 'broadcast'][:10]
    return render_template('admin/panel_notice.html', recent=recent)


@bp.post('/notice/send')
@staff_required
def notice_send():
    title = business.clean(request.form.get('title'), 40)
    text = business.clean(request.form.get('text'), 300)
    if not title or not text:
        flash('标题和内容都要填', 'warn')
    else:
        n = business.broadcast(title, text, request.form.get('scope') or 'all')
        business.audit(current_user().get('username'), role(), '群发通知：%s（%d 人）' % (title, n))
        flash('发出去了，共 %d 人收到' % n, 'ok')
    return redirect(url_for('admin.dashboard') + '#notice')


# ---------------------------------------------------------------- 举报处理
@staff_required
def reports_page():
    """客人举报的帖子，在这儿处理（删 / 忽略）"""
    return render_template('admin/panel_reports.html',
                           rows=sorted(db.rows('reports'), key=lambda x: -(x.get('at') or 0)))


@bp.post('/reports/<int:rid>/handle')
@staff_required
def report_handle(rid):
    act = request.form.get('act') or 'ignore'
    rows = db.rows('reports')
    hit = next((r for r in rows if r.get('id') == rid), None)
    if hit:
        hit['handled'] = True
        hit['handledBy'] = current_user().get('username')
        if act == 'del' and hit.get('kind') == 'post':
            db.write('posts', [p for p in db.rows('posts') if p.get('id') != hit.get('target')])
        db.write('reports', rows)
        business.audit(current_user().get('username'), role(),
                       '处理举报：%s' % ('删帖' if act == 'del' else '忽略'))
        flash('处理完成', 'ok')
    return redirect(url_for('admin.dashboard') + '#reports')


# ---------------------------------------------------------------- 备份 / 恢复
@staff_required
def backup_page():
    """数据备份与恢复（老版后台就有一页，出问题能一键回滚）"""
    files = []
    total = 0
    if os.path.isdir(DATA_DIR):
        for fn in sorted(os.listdir(DATA_DIR)):
            p = os.path.join(DATA_DIR, fn)
            if os.path.isfile(p) and (fn.endswith('.json') or fn.startswith('img')):
                files.append({'name': fn, 'size': os.path.getsize(p),
                              'time': time.strftime('%m-%d %H:%M', time.localtime(os.path.getmtime(p)))})
                total += os.path.getsize(p)
    return render_template('admin/panel_backup.html', files=files, total=total)


@bp.post('/backup/export')
@staff_required
def backup_export():
    """把 data 里所有 json 打包下载（不含密钥文件）"""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(DATA_DIR)):
            if fn.endswith('.json'):
                z.write(os.path.join(DATA_DIR, fn), fn)
        img_dir = os.path.join(DATA_DIR, 'img')
        if os.path.isdir(img_dir):
            for root, _dirs, names in os.walk(img_dir):
                for nm in names:
                    p = os.path.join(root, nm)
                    z.write(p, os.path.relpath(p, DATA_DIR))
    buf.seek(0)
    name = '甜薯备份-%s.zip' % time.strftime('%Y%m%d-%H%M')
    business.audit(current_user().get('username'), role(), '导出了数据备份')
    return send_file(buf, mimetype='application/zip', as_attachment=True, download_name=name)


@bp.post('/backup/import')
@staff_required
def backup_import():
    """导入备份 zip（会先自动备份当前数据，出问题还能再退回来）"""
    import io
    import shutil
    import zipfile

    f = request.files.get('zip')
    if not f or not f.filename:
        flash('先选一个备份 zip', 'warn')
        return redirect(url_for('admin.dashboard') + '#backup')
    keep = os.path.join(os.path.dirname(DATA_DIR), 'data_导入前-%s' % time.strftime('%Y%m%d-%H%M%S'))
    if os.path.isdir(DATA_DIR):
        shutil.copytree(DATA_DIR, keep)
    n = 0
    with zipfile.ZipFile(io.BytesIO(f.read())) as z:
        for nm in z.namelist():
            if nm.endswith('.json') or nm.startswith('img/'):
                if '..' in nm or nm.startswith('/'):
                    continue
                z.extract(nm, DATA_DIR)
                n += 1
    business.audit(current_user().get('username'), role(), '导入了备份（%d 个文件）' % n)
    flash('导入完成：%d 个文件。原来的数据留在 %s' % (n, os.path.basename(keep)), 'ok')
    return redirect(url_for('admin.dashboard') + '#backup')


# ---------------------------------------------------------------- 客户档案
@bp.get('/users/<phone>')
@staff_required
def user_detail(phone):
    """单个客户的档案：来过几次、花过多少、信用和余额流水、说过什么"""
    u = db.one('users', phone=phone)
    if not u:
        flash('没这个客户', 'warn')
        return redirect(url_for('admin.dashboard') + '#users')
    mine = [b for b in db.rows('bookings') if str(b.get('phone')) == str(phone)]
    msgs = [m for m in db.rows('messages') if str(m.get('phone')) == str(phone)]
    rvs = [r for r in db.rows('reviews') if str(r.get('phone')) == str(phone)]
    return render_template('admin/user_detail.html', u=u,
                           bookings=sorted(mine, key=lambda x: -(x.get('id') or 0)),
                           spent=sum(int(b.get('amount') or 0) for b in mine if b.get('status') != 'cancelled'),
                           msgs=sorted(msgs, key=lambda x: -(x.get('createdAt') or 0)),
                           reviews=sorted(rvs, key=lambda x: -(x.get('createdAt') or 0)))


# ---------------------------------------------------------------- 店客留言 / 社区
@staff_required
def messages():
    """客人留的言（没回的排前面）—— 晚到没车、想换时间、问价，基本都从这儿来"""
    rows = sorted(db.rows('messages'), key=lambda x: -(x.get('createdAt') or 0))
    status = request.args.get('status') or 'pending'     # 状态筛选在前端做
    return render_template('admin/panel_messages.html', rows=rows, status=status,
                           counts={k: len([m for m in db.rows('messages') if (m.get('status') or 'pending') == k])
                                   for k in ('pending', 'replied')})


@bp.post('/messages/<int:mid>/reply')
@staff_required
def message_reply(mid):
    text = business.clean(request.form.get('text'), 300)
    rows = db.rows('messages')
    hit = next((m for m in rows if m.get('id') == mid), None)
    if not hit:
        flash('没这条留言', 'warn')
    else:
        hit.update(status='replied', reply=text, repliedBy=current_user().get('username'),
                   repliedAt=business.now_ms())
        db.write('messages', rows)
        business.notify(hit.get('phone'), '店家回复了你的留言',
                        '你问「%s」，店家回：%s' % (hit.get('text', '')[:18], text), 'msg')
        flash('回复已发出', 'ok')
    return redirect(url_for('admin.dashboard') + '#messages')


@bp.post('/post/<int:pid>/del')
@staff_required
def post_del(pid):
    """删帖（广告、剧透不标注之类的）"""
    db.write('posts', [p for p in db.rows('posts') if p.get('id') != pid])
    business.audit(current_user().get('username'), role(), '删了社区帖 #%s' % pid)
    flash('帖子删了', 'ok')
    return redirect(url_for('public.comm'))


# ---------------------------------------------------------------- DM 结算
@staff_required
def dm_page():
    """DM 结算：这个月每个 DM 分成多少（分成 = 营业额 × 比例，指定加价另算）"""
    month = request.args.get('month') or __import__('time').strftime('%Y-%m')
    return render_template('admin/panel_dm.html', data=business.dm_settlement(month),
                           dms=[u for u in db.rows('users') if business.has_role(u, 'dm')])


@bp.post('/dm/settle')
@staff_required
def dm_settle():
    """标记某人这个月已结清（只记标记，不碰钱）"""
    month = request.form.get('month')
    phone = request.form.get('dmPhone')
    rows = db.rows('settles')
    hit = next((x for x in rows if x.get('month') == month and str(x.get('dmPhone')) == str(phone)), None)
    if hit:
        hit['settled'] = request.form.get('undo') != '1'
        hit['settledAt'] = business.now_ms()
        hit['settledBy'] = current_user().get('username')
    else:
        rows.append({'id': business.now_ms(), 'month': month, 'dmPhone': phone, 'settled': True,
                     'settledAt': business.now_ms(), 'settledBy': current_user().get('username')})
    db.write('settles', rows)
    flash('已标记 %s 的 %s 月结算' % (phone, month), 'ok')
    return redirect(url_for('admin.dashboard') + '#dm')


# ---------------------------------------------------------------- 后台标签总表
# 一个网址里切所有面板：/admin?tab=bookings 这样。
# 以后加新功能：先照抄一个视图函数，再来这里补一行，最后去 _nav.html 加个标签。
# （放在文件末尾是因为它要引用上面所有函数；dashboard() 里是运行时才查这张表，所以顺序没问题）
_TAB_FUNCS = {
    'dash': dash_panel, 'sessions': sessions, 'bookings': bookings, 'users': users,
    'growth': growth, 'reviews': reviews,
    'messages': messages, 'scripts': scripts, 'orders': orders, 'guides': guides_page,
    'notice': notice_page, 'dm': dm_page, 'backup': backup_page, 'reports': reports_page,
    'logs': logs,
}
