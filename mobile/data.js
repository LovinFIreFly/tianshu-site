/* ============================================================================
   手机端独立站 · 静态配置 + 离线兜底数据
   - MOBILE_STATIC：店铺名 / 金刚区 / 菜单（这些不依赖后端，前端常驻）
   - MOBILE_FALLBACK：剧本 / 场次 / 拼车 / 我的（接口连不上时兜底，保证能看）
   真实数据由 /m/api/* 提供，app.js 会优先用接口返回。
   ========================================================================== */
window.MOBILE_STATIC = {
  shop: { name: "甜薯剧本杀", notice: "周末场次紧张，建议提前两天订位 🍠" },

  nav: [
    { icon: "🎭", label: "沉浸本" },
    { icon: "🔍", label: "烧脑本" },
    { icon: "💞", label: "情感本" },
    { icon: "😂", label: "欢乐本" },
    { icon: "👻", label: "恐怖本" },
    { icon: "🚗", label: "拼车" },
    { icon: "📅", label: "组局" },
    { icon: "🏆", label: "榜单" },
    { icon: "🎁", label: "邀友" },
    { icon: "📍", label: "门店" },
  ],

  menu: [
    { icon: "📜", label: "我的预约" },
    { icon: "✍️", label: "我的评价" },
    { icon: "🎟️", label: "我的券包" },
    { icon: "👥", label: "邀友赚券" },
    { icon: "⚙️", label: "设置" },
  ],
};

window.MOBILE_FALLBACK = {
  scripts: [
    { id: 1, emoji: "🕯️", title: "雾隐村 · 山鬼", tags: ["沉浸", "恐怖", "7人"], players: 7, duration: "5h", difficulty: "进阶", price: 168, hot: true, grad: "linear-gradient(160deg,#3a2b4d,#15131f)", desc: "雨夜的湘西村寨，戏台上的山鬼究竟是人是鬼？\n\n一场把灯光、音效、NPC 全拉满的沉浸式恐怖本，胆小慎入。" },
    { id: 2, emoji: "🕵️", title: "雾都谜案", tags: ["推理", "硬核", "6人"], players: 6, duration: "4.5h", difficulty: "硬核", price: 138, hot: false, grad: "linear-gradient(160deg,#1f3a4d,#0f1b22)", desc: "一封匿名信，一桩无人生还的命案。\n\n逻辑链密不透风，适合喜欢真本格推理的老玩家。" },
    { id: 3, emoji: "💞", title: "我们的夏天", tags: ["情感", "治愈", "5人"], players: 5, duration: "4h", difficulty: "新手", price: 118, hot: true, grad: "linear-gradient(160deg,#4d3a2b,#221a13)", desc: "青春、遗憾、和没能说出口的话。\n\n不烧脑、不恐怖，适合情侣或第一次玩本的朋友。" },
    { id: 4, emoji: "😂", title: "欢乐村晚", tags: ["欢乐", "撕逼", "8人"], players: 8, duration: "3.5h", difficulty: "新手", price: 98, hot: false, grad: "linear-gradient(160deg,#2b4d3a,#13221a)", desc: "村晚小品既视感，全程爆笑。\n\n氛围组首选，破冰神器。" },
    { id: 5, emoji: "👑", title: "长安十二时辰", tags: ["机制", "阵营", "9人"], players: 9, duration: "6h", difficulty: "进阶", price: 188, hot: true, grad: "linear-gradient(160deg,#4d3b1f,#221a0f)", desc: "大唐风云，多方博弈。\n\n大机制本，权谋拉满。" },
    { id: 6, emoji: "🌃", title: "霓虹追凶", tags: ["都市", "反转", "6人"], players: 6, duration: "4h", difficulty: "进阶", price: 148, hot: false, grad: "linear-gradient(160deg,#2b2b4d,#131322)", desc: "赛博都市里的连环案，每一步都可能是反转。" },
    { id: 7, emoji: "🐺", title: "狼人杀之夜", tags: ["社交", "发言", "10人"], players: 10, duration: "3h", difficulty: "新手", price: 88, hot: false, grad: "linear-gradient(160deg,#3a1f1f,#1a0f0f)", desc: "经典阵营，纯靠嘴和演技。\n\n新手友好，店里有专业主持人带场。" },
    { id: 8, emoji: "🪐", title: "星海遗孤", tags: ["科幻", "情感", "7人"], players: 7, duration: "5h", difficulty: "进阶", price: 158, hot: false, grad: "linear-gradient(160deg,#1f2f4d,#0f1622)", desc: "末日星舰上的最后一夜。\n\n科幻外壳下的情感核，后劲很足。" },
  ],
  sessions: [
    { id: 101, time: "14:00", name: "雾隐村 · 山鬼", room: "A房 · 6座", cap: 7, have: 5, script: 1 },
    { id: 102, time: "16:30", name: "我们的夏天", room: "B房 · 8座", cap: 5, have: 2, script: 3 },
    { id: 103, time: "19:00", name: "长安十二时辰", room: "大房 · 10座", cap: 9, have: 6, script: 5 },
    { id: 104, time: "20:30", name: "霓虹追凶", room: "A房 · 6座", cap: 6, have: 4, script: 6 },
  ],
  cars: [
    { id: 201, who: "阿柿", av: "🍅", script: "雾隐村 · 山鬼", time: "周六 19:00", have: 3, need: 4, tags: ["新手友好", "不跳车"], note: "三个老玩家凑齐了，差一位小伙伴就能发车。" },
    { id: 202, who: "鹿鸣", av: "🦌", script: "雾都谜案", time: "周五 20:00", have: 2, need: 4, tags: ["硬核玩家"], note: "想找两个能盘逻辑的大佬。" },
    { id: 203, who: "小满", av: "🌾", script: "欢乐村晚", time: "周日 14:00", have: 5, need: 3, tags: ["准时到场"], note: "破冰局，欢迎第一次玩本的朋友。" },
    { id: 204, who: "夜行", av: "🌙", script: "星海遗孤", time: "周四 19:30", have: 4, need: 3, tags: ["不跳车"], note: "科幻情感本，希望队友别跳车。" },
  ],
  me: {
    name: "FireFly", initial: "🦋", phone: "135****8081", id: "TS0001", credit: 100,
    stats: { bookings: 23, reviews: 18, spent: 2680 },
  },
};
