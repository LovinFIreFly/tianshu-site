#!/usr/bin/env bash
# 甜薯剧本杀 · 推送重试（Linux / macOS / 服务器上用）
# 顺序换路，第一条通了就停：① 直连 ② 代理 ③ 国内镜像
# 用法：bash tools/push.sh [分支名] [代理地址]
set -u
BRANCH="${1:-python-rewrite}"
PROXY="${2:-http://127.0.0.1:12000}"
REPO="https://github.com/LovinFireFly/tianshu-site.git"
MIRRORS=(
  "https://ghproxy.com/https://github.com/LovinFireFly/tianshu-site.git"
  "https://gh-proxy.com/https://github.com/LovinFireFly/tianshu-site.git"
)

try_push () {   # $1=url  $2=proxy(可空)  $3=说明
  local url="$1" via="$2" label="$3"
  echo "  尝试：$label"
  local out
  if [ -n "$via" ]; then
    out=$(git -c "http.proxy=$via" push "$url" "$BRANCH:$BRANCH" 2>&1)
  else
    out=$(git push "$url" "$BRANCH:$BRANCH" 2>&1)
  fi
  if echo "$out" | grep -qE "$BRANCH -> $BRANCH|up-to-date"; then
    echo "  ✔ 推送成功（$label）"; exit 0
  fi
  echo "  ✘ 失败：$(echo "$out" | grep -E 'fatal|Failed|timed out|reset' | head -1)"
}

echo "推送分支：$BRANCH"
try_push "$REPO" "" "直连 GitHub"
[ -n "$PROXY" ] && try_push "$REPO" "$PROXY" "代理 $PROXY"
for m in "${MIRRORS[@]}"; do try_push "$m" "" "国内镜像 $m"; done

echo ""
echo "四条路都不通。备选："
echo "  1) 等网络恢复再跑一次"
echo "  2) git bundle create update.bundle HEAD  → 拷走再推"
echo "  3) 直接把改了的文件传服务器（不用 git），见 README「推不动时的兜底办法」"
exit 1
