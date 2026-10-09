const api = require('./utils/api')

App({
  globalData: { user: null, openid: '' },

  onLaunch() {
    const token = api.getToken()
    if (!token) {
      this.trySilentLogin()
    } else {
      this.checkToken(token)
    }
  },

  // 已有 token：校验一次
  checkToken(token) {
    api.get('/m/api/me').then((res) => {
      if (res.guest) {
        api.clearToken()
        this.trySilentLogin()
      } else {
        this.globalData.user = res
      }
    }).catch(() => {
      api.clearToken()
      this.trySilentLogin()
    })
  },

  // 无 token：尝试 wx.login 静默登录
  trySilentLogin() {
    api.doLoginOrBind().then((res) => {
      if (res.needBind) {
        this.globalData.openid = res.openid
        // 静默登录失败：未绑定，首页先加载；需要鉴权的页面会自动跳绑定
      } else if (res.ok) {
        this.globalData.user = { phone: res.phone, nick: res.nick }
      }
    }).catch((err) => {
      console.log('静默登录失败', err)
    })
  },

  setUser(user) {
    this.globalData.user = user
  }
})
