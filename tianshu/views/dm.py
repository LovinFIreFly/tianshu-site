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
    return render_template('dm/panel_today.html', sessions=mine, bookings=bookings,
                           today=business.day_label(business.midnight()), my_row=my_row, month=month['month'])


def _panel_html(key):
    """把面板渲染成一段 HTML —— 外壳页面要把它塞进 <div class="tabpane">"""
    r = _TAB_FUNCS[key]()
    return r.get_data(as_text=True) if hasattr(r, 'get_data') else str(r)


@bp.get('/')
@dm_required
def index():
    """DM 工作台 —— 唯一的入口页。

    三块内容（今日 / 我的客人 / 学本资料）都在这一页里渲染好，点标签只是前端切显示：
    不跳页、不改网址。所以不管点哪块，网址一直是 /dm。
    """
    return render_template('dm/shell.html', panels={k: _panel_html(k) for k in _TAB_FUNCS})


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
    """DM 自己编辑公开主页：风格 / 简介 / 接不接客人点名"""
    u = current_user()
    f = request.form
    users = db.rows('users')
    for x in users:
        if str(x.get('phone')) == str(u.get('phone')):
            pf = x.get('dmProfile') or {}
            pf['style'] = business.clean(f.get('style'), 20)
            pf['bio'] = business.clean(f.get('bio'), 200)
            pf['canOpen'] = f.get('canOpen') == '1'
            x['dmProfile'] = pf
    db.write('users', users)
    business.audit(u.get('username'), role(), '更新了自己的 DM 主页')
    flash('主页更新好了 —— 客人在剧本页点你的名字就能看到', 'ok')
    return redirect(url_for('dm.index') + '#growth')


# 标签总表（放末尾因为它要引用上面的函数；index() 里是运行时才查，顺序无所谓）
_TAB_FUNCS = {'today': today_panel, 'credit': credit, 'growth': growth, 'guides': guides}
