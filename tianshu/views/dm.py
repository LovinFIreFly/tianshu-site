# -*- coding: utf-8 -*-
"""
DM 工作台：对应老版那一整套 dm-* 界面

    /dm            今日我带哪几场、几个人、顺手核销 + 我这个月能拿多少
    /dm/credit     我场次里的客人（只看自己带过的，别人的看不到）
    /dm/guides     学本资料库（门店上传的解析/话术/复盘）+ 提练本申请

权限：DM 本人 / 管理员 / 超管（管理员代班时也能用）
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from tianshu import business
from tianshu.db import db
from tianshu.security import current_user, dm_required, is_dm, role

bp = Blueprint('dm', __name__, url_prefix='/dm')


@bp.get('/')
@dm_required
def index():
    """今日概览：我带哪几场、谁来了、本月分成多少"""
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
    return render_template('dm/index.html', sessions=mine, bookings=bookings,
                           today=business.day_label(business.midnight()), my_row=my_row, month=month['month'])


@bp.post('/verify')
@dm_required
def verify():
    """DM 也能核销（客人到店报码，谁在前台谁核）"""
    ok, msg, _b = business.verify_checkin(request.form.get('code'), current_user().get('username'))
    flash(msg, 'ok' if ok else 'warn')
    return redirect(url_for('dm.index'))


@bp.get('/credit')
@dm_required
def credit():
    """我带过的客人 + 改信用分（老版 dm-credit）"""
    u = current_user()
    return render_template('dm/credit.html', rows=business.dm_customers_of(str(u.get('phone'))))


@bp.post('/credit')
@dm_required
def credit_set():
    before, after = business.adjust_credit(
        request.form.get('phone'), request.form.get('delta'),
        business.clean(request.form.get('reason'), 40) or 'DM 调整', current_user().get('username'))
    flash('信用分 %s → %s' % (before, after) if before is not None else '没这个客人',
          'ok' if before is not None else 'warn')
    return redirect(url_for('dm.credit'))


@bp.get('/guides')
@dm_required
def guides():
    """学本资料库 + 我的练本申请（老版 dm-guides / 练本）"""
    u = current_user()
    return render_template('dm/guides.html', guides=business.guides(),
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
    return redirect(url_for('dm.guides'))
