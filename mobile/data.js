/* 离线兜底数据：接口拉不到时用它先渲染，保证页面不空 */
window.MOBILE_STATIC = {
  scripts: [
    { id:"n01", title:"门卫室的夜班日志", tags:["悬疑","推理"], players:"4 人", duration:"约 3.5h",
      difficulty:"中", price:0, hot:true,
      desc:"店里在装修，值夜班的人被临时安排到了传达室。窗外没有风，收音机自己换了台。这一夜，你们四个轮班的人，得搞清楚昨晚到底是谁没有锁门。",
      grad:"linear-gradient(160deg,#3a2b4d,#15131f)", cover:"/m/poster-n01.jpg" },
    { id:"n02", title:"第七把椅子", tags:["欢乐","剧情"], players:"5 人", duration:"约 2.5h",
      difficulty:"轻", price:0, hot:false,
      desc:"每周五清点椅子，柜子里总比名单多一把。这周多出的那把，椅背上刻着一个你们都不认识的名字。谁坐上去，谁就得讲一个关于它的故事。",
      grad:"linear-gradient(160deg,#4d3b1f,#221a0f)", cover:"/m/poster-n02.jpg" }
  ],
  sessions: [],
  cars: [],
  talks: [
    { name:"老赵", avatar:"", text:"夜班日志真的有点东西，门卫大叔的收音机自己换了三次台。", ago:"昨天" },
    { name:"阿禾", avatar:"", text:"第七把椅子还差两个人，周五晚上谁一起来？", ago:"今天" }
  ],
  me: { guest: true }
};
