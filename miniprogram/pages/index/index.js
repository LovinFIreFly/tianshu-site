const api = require('../../utils/api')

Page({
  data: { today: [], scripts: [], cars: [], talks: [], loading: true },

  onLoad() {
    this.loadAll()
  },

  onPullDownRefresh() {
    this.loadAll().then(() => wx.stopPullDownRefresh())
  },

  loadAll() {
    this.setData({ loading: true })
    return Promise.all([
      api.get('/m/api/sessions'),
      api.get('/m/api/scripts', { limit: 6 }),
      api.get('/m/api/cars', { limit: 5 }),
      api.get('/m/api/talks', { limit: 3 })
    ]).then(([sessions, scripts, cars, talks]) => {
      this.setData({
        today: sessions.sessions || [],
        scripts: scripts.list || [],
        cars: cars.list || [],
        talks: talks.list || [],
        loading: false
      })
    }).catch(() => {
      this.setData({ loading: false })
    })
  },

  goScripts() { wx.switchTab({ url: '/pages/scripts/scripts' }) },
  goCarpool() { wx.switchTab({ url: '/pages/carpool/carpool' }) },
  goScript(e) {
    wx.navigateTo({ url: '/pages/scriptDetail/scriptDetail?sid=' + e.currentTarget.dataset.sid })
  },
  goCar(e) {
    wx.navigateTo({ url: '/pages/carpool/carpool?cid=' + e.currentTarget.dataset.cid })
  }
})
