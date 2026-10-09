const api = require('../../utils/api')
const app = getApp()

Page({
  data: { phone: '', password: '', loading: false },

  onInputPhone(e) { this.setData({ phone: e.detail.value }) },
  onInputPwd(e) { this.setData({ password: e.detail.value }) },

  submit() {
    const { phone, password } = this.data
    if (!phone || !password) {
      wx.showToast({ title: '请填写手机号和密码', icon: 'none' })
      return
    }
    this.setData({ loading: true })
    const openid = wx.getStorageSync('openid') || ''
    api.doLoginOrBind({ phone, password, openid }).then((res) => {
      this.setData({ loading: false })
      if (res.ok && res.token) {
        app.setUser({ phone: res.phone, nick: res.nick })
        wx.showToast({ title: '登录成功', icon: 'success' })
        setTimeout(() => wx.switchTab({ url: '/pages/me/me' }), 800)
      } else {
        wx.showToast({ title: res.msg || '登录失败', icon: 'none' })
      }
    }).catch((err) => {
      this.setData({ loading: false })
      wx.showToast({ title: err.msg || err || '登录失败', icon: 'none' })
    })
  },

  guest() {
    wx.switchTab({ url: '/pages/index/index' })
  }
})
