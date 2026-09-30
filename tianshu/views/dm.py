# -*- coding: utf-8 -*-
"""
DM 工作台：对应老版那一整套 dm-* 界面

    /dm            就这一个网址。三块内容都在这一页里，点标签前端切（不改网址）：
                     · 今日        我带哪几场、几个人、顺手核销 + 这个月能拿多少
                     · 我的客人    只看自己带过的客人，别人的看不到
                     · 学本资料    门店上传的解析/话术/复盘 + 提练本申请

权限：DM 本人 / 管理员 / 超管（管理员代班时也能用）
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from tianshu import business
from tianshu.db import db
from tianshu.security import current_user, dm_required, is_dm, role

bp = Blueprint('dm', __name__, url_prefix='/dm')


def today_panel():
    """今日面板：我带哪几场、谁到场、顺手核销（就是老版 /dm 那一屏）"""
    u = current_user()
    phone = str(u.get('phone'))
    today = business.today_sessions()
    mine = [s for s in today if str(s.get('dm')) == phone]
    sids = {s.get('id') for s in mine}
    bookings = [b for b in db.rows('bookings') if b.get('status') in ('booked', 'arrived')
                and (b.get('sessionId') in sids or str(b.get('dmPhone')) == phone)]
    bookings.sort(key=lambda x: str(x.get('time')))
    month = business.dm_settlement()
    my_row = next((r for r in month['rows'] if str(r.get('dmPhone')) == phone), None)
    # 我带的场里，有谁的尾款等着确认（客人在支付页点过"我已完成支付"的）
    pays = {str(x.get('bid')): x for x in db.rows('pays')}
    bal_wait = []
    for b in db.rows('bookings'):
        if b.get('status') not in ('arrived', 'done') or b.get('sessionId') not in sids:
            continue
        o = pays.get(str(b.get('id')))
        if o and o.get('balStatus') == 'claimed':
            bal_wait.append({'b': b, 'o': o,
                             'bal': max(0, int(o.get('amount') or 0) - int(o.get('deposit') or 0))})
    return render_template('dm/panel_today.html', sessions=mine, bookings=bookings,
                           today=business.day_label(business.midnight()), my_row=my_row,
                           month=month['month'], bal_wait=bal_wait)


@bp.post('/orders/<int:oid>/confirm-bal')
@dm_required
def confirm_bal(oid):
    """DM 确认收到尾款（带完本当场收钱最方便）—— 确认完客人才解锁点评"""
    ok, msg = business.order_action(current_user(), oid, 'pay-bal', is_staff=True)
    flash(msg, 'ok' if ok else 'warn')
    return redirect(url_for('dm.index') + '#today')


def _panel_html(key):
    """把面板渲染成一段 HTML —— 外壳页面要把它塞进 <div class="tabpane">"""
    r = _TAB_FUNCS[key]()
    return r.get_data(as_text=True) if hasattr(r, 'get_data') else str(r)


@bp.get('/')
@dm_required
def index():
    """DM 工作台 —— 唯一的入口页。

    三块内容（今日 / 我的客人 / 学本资料…）原来一次全渲染，现在首屏只算当前 tab（默认 today），
    其余面板留占位；切 tab 时前端 fetch /dm/?partial=1&tab=xxx 单独拉（AUD-B-0002/P0-2）。

    ※ 前端配合：tabs.js 切 tab 时需对未加载面板 fetch partial=1&tab=xxx 并替换占位。
      本轮仅落地后端侧，tabs.js 改造由前端代理（H1/H2）完成。
    """
    tab = request.args.get('tab') or 'today'
    func = _TAB_FUNCS.get(tab) or _TAB_FUNCS['today']
    if request.args.get('partial') == '1':
        return func()                      # 前端 fetch 单个面板
    panels = {k: (('<!-- panel:%s -->' % k) if k != tab else _panel_html(k)) for k in _TAB_FUNCS}
    return render_template('dm/shell.html', panels=panels, active=tab)


@bp.post('/verify')
@dm_required
def verify():
    """DM 也能核销（客人到店报码，谁在前台谁核）"""
    ok, msg, _b = business.verify_checkin(request.form.get('code'), current_user().get('username'))
    flash(msg, 'ok' if ok else 'warn')
    return redirect(url_for('dm.index'))


@dm_required
def credit():
    """我带过的客人 + 改信用分（老版 dm-credit）"""
    u = current_user()
    return render_template('dm/panel_credit.html', rows=business.dm_customers_of(str(u.get('phone'))))


@bp.post('/credit')
@dm_required
def credit_set():
    before, after = business.adjust_credit(
        request.form.get('phone'), request.form.get('delta'),
        business.clean(request.form.get('reason'), 40) or 'DM 调整', current_user().get('username'))
    flash('信用分 %s → %s' % (before, after) if before is not None else '没这个客人',
          'ok' if before is not None else 'warn')
    return redirect(url_for('dm.index') + '#credit')


@dm_required
def guides():
    """学本资料库 + 我的练本申请（老版 dm-guides / 练本）"""
    u = current_user()
    return render_template('dm/panel_guides.html', guides=business.guides(),
                           mine=[p for p in db.rows('practices') if str(p.get('phone')) == str(u.get('phone'))],
                           scripts=db.rows('scripts'))


@bp.post('/practices')
@dm_required
def practice_new():
    """提练本申请：想练哪个本、希望什么时候"""
    u = current_user()
    db.update('practices', lambda rows: rows + [{
        'id': business.now_ms(), 'phone': u.get('phone'), 'username': u.get('username'),
        'sid': request.form.get('sid'), 'ts': int(request.form.get('ts') or 0),
        'note': business.clean(request.form.get('note'), 100), 'status': 'pending',
        'at': business.now_ms()}])
    business.audit(u.get('username'), role(), '提交了练本申请')
    flash('练本申请提交啦，等门店安排', 'ok')
    return redirect(url_for('dm.index') + '#guides')


@dm_required
def growth():
    """我的成长（老版 dm-stats + dm-me 合成一块）：段位、带本量、好评率、指定次数，
    外加编辑自己的公开主页 —— 客人能在剧本页点进来看到这段介绍"""
    u = current_user()
    return render_template('dm/panel_growth.html', st=business.dm_growth(str(u.get('phone'))), u=u)


@bp.post('/profile')
@dm_required
def profile_save():
    """DM 自己编辑公开主页：形象照 / 风格 / 简介 / 接不接客人点名

    形象照存在 data/img/dm/ 下（跟数据一起备份、搬家不丢），
    客人打开你的公开主页就能看到；想换再传一张，勾「删掉」就撤下来。
    """
    u = current_user()
    f = request.form
    users = db.rows('users')
    flash_photo = ''
    for x in users:
        if str(x.get('phone')) == str(u.get('phone')):
            pf = x.get('dmProfile') or {}
            pf['style'] = business.clean(f.get('style'), 20)
            pf['bio'] = business.clean(f.get('bio'), 200)
            pf['canOpen'] = f.get('canOpen') == '1'
            if f.get('del_photo') == '1':
                pf['photo'] = ''
            url, err = business.save_upload(request.files.get('photo'), 'dm')
            if url:
                pf['photo'] = url
            elif err and request.files.get('photo') and request.files['photo'].filename:
                flash('形象照没传上：%s' % err, 'warn')
            x['dmProfile'] = pf
            if pf.get('photo'):
                flash_photo = ' 形象照也换好了。'
    db.write('users', users)
    business.audit(u.get('username'), role(), '更新了自己的 DM 主页%s'
                   % ('（含形象照）' if flash_photo else ''))
    flash('主页更新好了 —— 客人在剧本页点你的名字就能看到。%s' % flash_photo, 'ok')
    return redirect(url_for('dm.index') + '#growth')


@dm_required
def msgs():
    """我的消息（老版 dm-msgs）：门店发给我的通知 + 我场次客人留的言。

    通知里会有：排班变动、场次取消、练本申请处理结果、被点名等等。
    客人留言 DM 只能看，回复还是门店来 —— 免得口径不一致。
    """
    u = current_user()
    phone = str(u.get('phone'))
    notices = [dict(n, to=None) for n in db.rows('notices')
               if not n.get('to') or phone in [str(p) for p in (n.get('to') or [])]]
    notices.sort(key=lambda x: -(x.get('at') or 0))
    unread = len([n for n in notices if phone not in [str(p) for p in (n.get('readBy') or [])]])
    mine = {str(x.get('phone')) for x in business.dm_customers_of(phone)}
    guest = sorted([m for m in db.rows('messages')
                    if str(m.get('phone')) in mine and (m.get('status') or 'pending') == 'pending'],
                   key=lambda x: -(x.get('createdAt') or 0))[:10]
    return render_template('dm/panel_msgs.html', rows=notices[:40], unread=unread, guest=guest)


@dm_required
def sched():
    """我的档期（老版 dm-sched）：从今天起排在我名下的场次，按时间排。

    这里只看"还没开场"的；带完的场次在「今日场次」和「我的成长」里看。
    """
    u = current_user()
    phone = str(u.get('phone'))
    t0 = business.midnight()
    bookings = db.rows('bookings')
    out = []
    for s in db.rows('sessions'):
        if str(s.get('dm')) != phone or (s.get('ts') or 0) < t0 or s.get('status') == 'cancelled':
            continue
        joined = sum((b.get('players') or 1) for b in bookings
                     if b.get('sessionId') == s.get('id') and b.get('status') != 'cancelled')
        out.append(dict(s, joined=joined))
    out.sort(key=lambda x: ((x.get('ts') or 0), str(x.get('time'))))
    return render_template('dm/panel_sched.html', rows=out)


@dm_required
def talktips_panel():
    """开本话术库（DM 与 admin 共用 admin/panel_talktips.html；增删走 /admin/talktips/*，
    该路由用 dm_required 闸门、business 内二次判权，DM 可维护）。"""
    cat = request.args.get('cat') or ''
    return render_template('admin/panel_talktips.html',
                           rows=business.talktips(cat), cat=cat,
                           cats=getattr(business, 'TALKTIP_CATS', ('开场白', '过渡', '结尾', '其他')))


# 标签总表（放末尾因为它要引用上面的函数；index() 里是运行时才查，顺序无所谓）
_TAB_FUNCS = {'msgs': msgs, 'today': today_panel, 'credit': credit,
              'sched': sched, 'growth': growth, 'guides': guides,
              'talktips': talktips_panel}
