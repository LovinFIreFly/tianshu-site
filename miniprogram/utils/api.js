const BASE = 'https://tianshu.lovinfirefly.cn'

function getToken() {
  return wx.getStorageSync('token') || ''
}

function setToken(token) {
  wx.setStorageSync('token', token)
}

function clearToken() {
  wx.removeStorageSync('token')
}

function request(method, url, data = {}) {
  return new Promise((resolve, reject) => {
    const token = getToken()
    const headers = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = 'Bearer ' + token
    wx.request({
      url: BASE + url,
      method: method,
      data: data,
      header: headers,
      success: (res) => {
        // 鉴权失败：跳到绑定页
        if (res.statusCode === 401 || (res.data && res.data.ok === false && /token|登录|绑定/.test(res.data.msg || ''))) {
          clearToken()
          wx.reLaunch({ url: '/pages/bind/bind' })
          return reject(res.data)
        }
        resolve(res.data)
      },
      fail: (err) => {
        wx.showToast({ title: '网络开小差了', icon: 'none' })
        reject(err)
      }
    })
  })
}

function get(url, data) { return request('GET', url, data) }
function post(url, data) { return request('POST', url, data) }

// 小程序登录/绑定主流程
function doLoginOrBind(bindData) {
  return new Promise((resolve, reject) => {
    wx.login({
      success: (loginRes) => {
        if (!loginRes.code) return reject('wx.login 失败')
        const payload = bindData ? { ...bindData, code: loginRes.code } : { code: loginRes.code }
        const url = bindData ? '/m/api/mp/bind' : '/m/api/mp/login'
        post(url, payload).then((r) => {
          if (r.ok && r.token) {
            setToken(r.token)
            wx.setStorageSync('openid', r.openid || '')
            resolve(r)
          } else if (!bindData && r.needBind) {
            wx.setStorageSync('openid', r.openid || '')
            resolve(r) // 需要走绑定页
          } else {
            reject(r.msg || '登录失败')
          }
        }).catch(reject)
      },
      fail: reject
    })
  })
}

// 拉起订阅消息授权（可在用户点击预约/取消时调用）
function requestSubscribe(tmplIds) {
  if (!tmplIds || !tmplIds.length) return Promise.resolve({})
  return new Promise((resolve) => {
    wx.requestSubscribeMessage({
      tmplIds: tmplIds,
      success: (res) => resolve(res),
      fail: () => resolve({})
    })
  })
}

module.exports = {
  BASE, getToken, setToken, clearToken,
  request, get, post, doLoginOrBind, requestSubscribe
}
