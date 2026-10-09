const api = require('../../utils/api')

Page({
  data: { list: [], page: 1, loading: false },
  onLoad() { this.load() },
  onPullDownRefresh() { this.setData({ page: 1 }); this.load().then(() => wx.stopPullDownRefresh()) },
  onReachBottom() { this.load(true) },

  load(more = false) {
    if (this.data.loading) return
    this.setData({ loading: true })
    const page = more ? this.data.page + 1 : 1
    return api.get('/m/api/cars', { page: page, limit: 10 }).then((res) => {
      const list = more ? [...this.data.list, ...(res.list || [])] : (res.list || [])
      this.setData({ list, page, loading: false })
    }).catch(() => this.setData({ loading: false }))
  }
})
