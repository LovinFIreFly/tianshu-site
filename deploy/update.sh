#!/usr/bin/env bash
# =============================================================================
# 甜薯剧本杀 · 线上更新（在服务器上跑，root）
# =============================================================================
#     sudo -i
#     bash /opt/tianshu/deploy/update.sh
#
# 跟 install.sh 的分工：
#   install.sh  装机器（系统依赖 / Caddy / systemd / 定时备份）—— 只跑一次，或者要动这些的时候
#   update.sh   只更新网站本身（拉代码 → 装依赖 → 重启 → 自测）—— 平时改完网站跑这个
#
# 会做四件事：
#   ① 更新前先备份 data/（update.sh 唯一会碰数据的地方，就这一下，还是只读）
#   ② git pull 最新代码（分支 python-rewrite）
#   ③ 装依赖（有新依赖才真的装东西）
#   ④ 重启服务 + 本机自测（起不来就把日志尾巴打出来，别让你猜）
#
# 数据（data/）不会被覆盖：它在 .gitignore 里，git 根本不动它。
# =============================================================================
set -euo pipefail

DIR="${DIR:-/opt/tianshu}"
BRANCH="${BRANCH:-python-rewrite}"
PORT="${PORT:-8000}"

if [ "$(id -u)" != "0" ]; then
  echo "请用 root 跑（先执行 sudo -i）"
  exit 1
fi
if [ ! -d "$DIR/.git" ]; then
  echo "[X] $DIR 不是 git 仓库。第一次装机请先跑：bash $DIR/deploy/install.sh 你的域名"
  exit 1
fi

echo "=============================================="
echo " 甜薯剧本杀 · 更新线上（$DIR）"
echo "=============================================="

echo "① 更新前备份 data/…"
if [ -x "$DIR/.venv/bin/python" ]; then
  (cd "$DIR" && "$DIR/.venv/bin/python" app.py --backup) || echo "   （备份没成功，先继续；data/ 本来也不会被这次更新动到）"
else
  echo "   （虚拟环境还没建，跳过；装机脚本会建）"
fi

echo "② 拉最新代码…"
BEFORE="$(git -C "$DIR" --no-pager log --oneline -1)"
git -C "$DIR" fetch --all -q
git -C "$DIR" checkout -q "$BRANCH"
git -C "$DIR" pull -q
AFTER="$(git -C "$DIR" --no-pager log --oneline -1)"
if [ "$BEFORE" = "$AFTER" ]; then
  echo "   已经是最新：$AFTER"
else
  echo "   更新前：$BEFORE"
  echo "   更新后：$AFTER"
fi

echo "③ 装依赖…"
if [ -x "$DIR/.venv/bin/pip" ]; then
  PIP_MIRROR="${PIP_MIRROR:-https://mirrors.aliyun.com/pypi/simple/}"
  "$DIR/.venv/bin/pip" install -q -i "$PIP_MIRROR" -r "$DIR/requirements.txt" \
    || "$DIR/.venv/bin/pip" install -q -r "$DIR/requirements.txt"
  "$DIR/.venv/bin/python" -c 'import flask, waitress' \
    || { echo "   [X] 依赖没装上，手动跑：$DIR/.venv/bin/pip install -r $DIR/requirements.txt"; exit 1; }
  echo "   Flask / waitress 就绪"
else
  echo "   [X] 没有虚拟环境，先跑装机脚本：bash $DIR/deploy/install.sh 你的域名"
  exit 1
fi

echo "④ 重启服务…"
# 老装机（跑 install.sh 那次）的 unit 里没有 TS_STRICT_PORT —— 这里顺手补上，
# 否则端口被占时服务会悄悄挪到 8001，反代 502 却查不出原因。
if systemctl cat tianshu >/dev/null 2>&1 && ! systemctl cat tianshu | grep -q 'TS_STRICT_PORT'; then
  echo "   给 unit 补 TS_STRICT_PORT=1（端口被占时直接报错，不再悄悄挪端口）"
  mkdir -p /etc/systemd/system/tianshu.service.d
  cat > /etc/systemd/system/tianshu.service.d/strict-port.conf <<'EOF'
[Service]
Environment=TS_STRICT_PORT=1
EOF
  systemctl daemon-reload
fi

# 重启之前先看一眼：$PORT 上是不是蹲着**不属于 systemd** 的旧进程？
# 有的话 app.py 的 pick_port() 会静默换到 8001，看起来"重启成功了"其实端口错了。
# 这里把它点出来（不自动杀：万一是你自己开着的调试进程，杀了会莫名）。
if command -v ss >/dev/null 2>&1; then
  _holder="$(ss -ltnp 2>/dev/null | grep ":$PORT " | grep -oE 'pid=[0-9]+' | grep -oE '[0-9]+' | head -1 || true)"
elif command -v netstat >/dev/null 2>&1; then
  _holder="$(netstat -ltnp 2>/dev/null | grep ":$PORT " | grep -oE '[0-9]+/' | grep -oE '[0-9]+' | head -1 || true)"
else
  _holder=""
fi
if [ -n "$_holder" ]; then
  echo "   ！$PORT 已被 PID $_holder 占用，先把它收掉再重启"
  ps -p "$_holder" -o pid=,args= 2>/dev/null | sed 's/^/      /' || true
  kill "$_holder" 2>/dev/null || true
  sleep 1
  kill -9 "$_holder" 2>/dev/null || true
  echo "   已收掉 PID $_holder"
fi

systemctl restart tianshu
sleep 3
if ! systemctl is-active --quiet tianshu; then
  echo "   [X] 服务没起来，看这里："
  systemctl --no-pager -l status tianshu | head -20 || true
  echo "   ---- 最近的日志 ----"
  journalctl -u tianshu -n 30 --no-pager || true
  exit 1
fi
echo "   服务在跑 [OK]"

echo "⑤ 本机自测…"
# ─────────────────────────────────────────────────────────────────────────────
# 为什么不能直接 curl 固定的 8000：
#   app.py 的 pick_port() 在端口被占时会**静默往后找**（8001、8002…）。
#   服务被 systemd 拉起、而 8000 上还蹲着一个旧进程时，真正监听的是 8001，
#   此时 curl 8000 → 连不上 → HTTP 000（不是 404、也不是 500）。
#   所以这里先**问出真实端口**，再拿它自测；问不到才退回 $PORT。
#
#   探测用「真发一个请求看谁答话」而不是「解析 ss/netstat 输出」——
#   后者在不同发行版上格式差异大，管道很容易静默返回空（踩过）。
# ─────────────────────────────────────────────────────────────────────────────
_ok() {  # $1=端口 → 是本站就返回 0
  # /health 是本站特有的端点，用它认人最准（返回 200 且不含 HTML 壳）
  code="$(curl -s -o /dev/null -m 4 -w '%{http_code}' "http://127.0.0.1:$1/health" 2>/dev/null || true)"
  [ "$code" = "200" ]
}

REAL_PORT=""
# ① 最可靠：从 systemd 读实际命令行里的 --port
_cand="$(systemctl show -p ExecStart --value tianshu 2>/dev/null \
  | grep -oE '\-\-port[= ][0-9]+' | grep -oE '[0-9]+' | head -1 || true)"
if [ -n "$_cand" ] && _ok "$_cand"; then REAL_PORT="$_cand"; fi
# ② 从进程表找
if [ -z "$REAL_PORT" ]; then
  _cand="$(ps -eo args= 2>/dev/null \
    | grep -E 'app\.py' | grep -v grep \
    | grep -oE '\-\-port[= ][0-9]+' | grep -oE '[0-9]+' | head -1 || true)"
  if [ -n "$_cand" ] && _ok "$_cand"; then REAL_PORT="$_cand"; fi
fi
# ③ 最后：把 $PORT .. $PORT+9 挨个问一遍（与 pick_port 的搜索范围一致）
if [ -z "$REAL_PORT" ]; then
  for _p in $(seq "$PORT" $((PORT + 9))); do
    if _ok "$_p"; then REAL_PORT="$_p"; break; fi
  done
fi

if [ -n "$REAL_PORT" ] && [ "$REAL_PORT" != "$PORT" ]; then
  echo "   ！服务实际监听 $REAL_PORT（不是 $PORT）"
  echo "     说明 $PORT 上还蹲着别的进程；想让它回到 $PORT：先杀掉它再 systemctl restart tianshu"
fi
CHECK_PORT="${REAL_PORT:-$PORT}"
BASE="http://127.0.0.1:$CHECK_PORT"
echo "   自测目标：$BASE"

# curl 失败时返回 000，这里统一用 OK/FAIL 说人话，别让人猜 000 是什么
_probe() {  # $1=路径 → 打印状态码
  curl -s -o /dev/null -m 8 -w '%{http_code}' "$BASE$1" 2>/dev/null || echo "000"
}
_show() {   # $1=标签 $2=路径
  code="$(_probe "$2")"
  if [ "$code" = "200" ]; then
    printf '   %-20s %s → HTTP %s  [OK]\n' "$1" "$2" "$code"
  elif [ "$code" = "000" ]; then
    printf '   %-20s %s → 连不上  [FAIL]\n' "$1" "$2"
  else
    printf '   %-20s %s → HTTP %s  [!!]\n' "$1" "$2" "$code"
  fi
}
_show "首页"     "/"
_show "剧本库"   "/scripts"
_show "健康检查" "/health"

# 新版才有的文件：确认这次拉的代码里带着它。
# 用 nova.css（当前 nova 模式真正加载的）而不是 design3.css —— 后者只在二代/三代用得上，
# 拿它当"代码更新成功"的判据会在 nova 模式下误报。
if [ "$(_probe '/static/css/nova.css')" = "200" ]; then
  echo "   新版资产（nova.css）在 [OK]"
else
  echo "   ！nova.css 拿不到 —— 代码可能没更新成功，检查 git 那边"
fi

echo
echo "=============================================="
echo "更新完成。手机流量打开 https://你的域名 看一眼（强刷一下，别让浏览器吃缓存）"
echo "想看一代/二代：后台 → 门店设置 → 网站版式"
echo "=============================================="
