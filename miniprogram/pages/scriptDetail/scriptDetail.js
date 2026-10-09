const api = require('../../utils/api')

Page({
  data: { sid: null, script: null, reviews: [], loading: true },

  onLoad(options) {
    this.setData({ sid: options.sid })
    this.load(options.sid)
  },

  load(sid) {
    this.setData({ loading: true })
    return Promise.all([
      api.get('/m/api/scripts/' + sid),
      api.get('/m/api/reviews', { sid: sid, limit: 10 })
    ]).then(([script, reviews]) => {
      this.setData({ script: script, reviews: reviews.list || [], loading: false })
    }).catch(() => this.setData({ loading: false }))
  },

  book() {
    wx.navigateTo({ url: '/pages/carpool/carpool?sid=' + this.data.sid })
  }
})
