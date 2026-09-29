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
curl -s -o /dev/null -w "   http://127.0.0.1:$PORT/         → HTTP %{http_code}\n" "http://127.0.0.1:$PORT/" || true
curl -s -o /dev/null -w "   http://127.0.0.1:$PORT/scripts  → HTTP %{http_code}\n" "http://127.0.0.1:$PORT/scripts" || true
curl -s -o /dev/null -w "   http://127.0.0.1:$PORT/health   → HTTP %{http_code}\n" "http://127.0.0.1:$PORT/health" || true
# 新版才有的文件：确认这次拉的代码里带着它（404 = 代码还是旧的）
if [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/static/css/design3.css")" = "200" ]; then
  echo "   新骨架（design3.css）在 [OK]"
else
  echo "   ！design3.css 还是 404 —— 代码可能没更新成功，检查 git 那边"
fi

echo
echo "=============================================="
echo "更新完成。手机流量打开 https://你的域名 看一眼（强刷一下，别让浏览器吃缓存）"
echo "想看一代/二代：后台 → 门店设置 → 网站版式"
echo "=============================================="
