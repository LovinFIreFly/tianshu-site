const api = require('../../utils/api')
const app = getApp()

Page({
  data: { user: null, loading: true },
  onShow() {
    this.load()
  },
  load() {
    this.setData({ loading: true })
    return api.get('/m/api/me').then((res) => {
      if (res.guest) {
        this.setData({ user: null, loading: false })
        wx.navigateTo({ url: '/pages/bind/bind' })
      } else {
        app.setUser(res)
        this.setData({ user: res, loading: false })
      }
    }).catch(() => this.setData({ loading: false }))
  },
  goBind() {
    wx.navigateTo({ url: '/pages/bind/bind' })
  },
  logout() {
    api.clearToken()
    this.setData({ user: null })
    wx.showToast({ title: '已退出', icon: 'none' })
  }
})
