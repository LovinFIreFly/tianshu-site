#!/usr/bin/env bash
# =============================================================================
# 甜薯剧本杀 · 云服务器一键部署（Ubuntu 22.04 / 24.04 适用）
# =============================================================================
# 在服务器上跑（root）：
#     sudo -i
#     cd /opt/tianshu && bash deploy/install.sh tianshu.lovinfirefly.cn
#
# 它会做完这几件事（重复跑也没事，等于"更新并重启"）：
#   ① 装系统依赖（python3 / venv / git）
#   ② 拉代码（GitHub 的 python-rewrite 分支）
#   ③ 用虚拟环境装 Python 依赖（不污染系统 Python，Ubuntu 24 也照跑）
#   ④ 装 Caddy —— 自动申请 HTTPS 证书、自动续期，反代到本机 8000
#   ⑤ 写 systemd 服务：崩溃自动重启、开机自启
#   ⑥ 加一条每天备份数据的定时任务（保留 14 天）
#
# 注意：8000 端口只在本机监听（app.py 默认 127.0.0.1），外面只开 80/443 ——
#       外面访问一律走 Caddy 的 https，比直接暴露 8000 安全。
# =============================================================================
set -euo pipefail

DOMAIN="${1:-}"
REPO="${REPO:-https://github.com/LovinFireFly/tianshu-site.git}"
BRANCH="${BRANCH:-python-rewrite}"
DIR="${DIR:-/opt/tianshu}"
PORT="${PORT:-8000}"

if [ -z "$DOMAIN" ]; then
  echo "用法：bash deploy/install.sh 你的域名"
  echo "例：  bash deploy/install.sh tianshu.lovinfirefly.cn"
  exit 1
fi
if [ "$(id -u)" != "0" ]; then
  echo "请用 root 跑（先执行 sudo -i）"
  exit 1
fi

echo "=============================================="
echo " 甜薯剧本杀 · 部署到这台服务器"
echo " 域名：$DOMAIN    目录：$DIR    分支：$BRANCH"
echo "=============================================="

echo "① 装系统依赖…"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git curl gnupg \
  debian-keyring debian-archive-keyring apt-transport-https

echo "② 取代码…"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch --all -q
  git -C "$DIR" checkout -q "$BRANCH"
  git -C "$DIR" pull -q
  echo "   已更新到最新：$(git -C "$DIR" --no-pager log --oneline -1)"
elif [ -d "$DIR" ] && [ -n "$(ls -A "$DIR" 2>/dev/null)" ]; then
  # 目录已经存在、但还不是 git 仓库 —— 常见于"先把 data 传上来了"。
  # 就地初始化：data/ 在 .gitignore 里，不会被覆盖，放心。
  echo "   $DIR 已有东西（可能是你先前传的 data），就地初始化…"
  git -C "$DIR" init -q
  git -C "$DIR" remote remove origin 2>/dev/null || true
  git -C "$DIR" remote add origin "$REPO"
  git -C "$DIR" fetch -q origin "$BRANCH"
  git -C "$DIR" checkout -q -B "$BRANCH" "origin/$BRANCH"
  echo "   已拉取：$(git -C "$DIR" --no-pager log --oneline -1)"
else
  git clone -q -b "$BRANCH" "$REPO" "$DIR"
  echo "   已拉取：$(git -C "$DIR" --no-pager log --oneline -1)"
fi

echo "③ 装 Python 依赖（虚拟环境 $DIR/.venv）…"
[ -d "$DIR/.venv" ] || python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install -q --upgrade pip
"$DIR/.venv/bin/pip" install -q -r "$DIR/requirements.txt"

echo "④ 装 Caddy（自动 HTTPS）…"
if ! command -v caddy >/dev/null 2>&1; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq
  apt-get install -y -qq caddy
fi

echo "⑤ 写 systemd 服务与 Caddy 配置…"
cat > /etc/systemd/system/tianshu.service <<EOF
[Unit]
Description=甜薯剧本杀（Flask + waitress）
After=network.target

[Service]
WorkingDirectory=$DIR
ExecStart=$DIR/.venv/bin/python $DIR/app.py --no-browser --port $PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/caddy/Caddyfile <<EOF
# 甜薯剧本杀 —— Caddy 自动申请并续期 HTTPS 证书，再转发给本机的网站
$DOMAIN {
	encode gzip
	reverse_proxy 127.0.0.1:$PORT
}
EOF

systemctl daemon-reload
systemctl enable -q --now tianshu
systemctl enable -q --now caddy
systemctl reload caddy 2>/dev/null || systemctl restart caddy

echo "⑥ 加每天备份数据的定时任务…"
if command -v crontab >/dev/null 2>&1; then
  CRON1="10 4 * * * cd $DIR && $DIR/.venv/bin/python app.py --backup >/dev/null 2>&1"
  CRON2="40 4 * * * find $DIR -maxdepth 1 -name '*.zip' -mtime +14 -delete >/dev/null 2>&1"
  TMPCRON="$(mktemp)"
  # 先剔除本脚本以前加过的那两行，再加回去（重复跑不会攒一堆）
  # 注意：crontab -l 在"还没有任何定时任务"时会返回非 0，grep 匹配不到也会返回非 0 ——
  # 这里 set -e + pipefail 会直接让脚本退出，所以必须 || true
  { crontab -l 2>/dev/null || true; } | grep -v 'app.py --backup' | grep -v '/maxdepth 1 -name' > "$TMPCRON" || true
  echo "$CRON1" >> "$TMPCRON"
  echo "$CRON2" >> "$TMPCRON"
  crontab "$TMPCRON"
  rm -f "$TMPCRON"
  echo "   每天 4:10 备份、4:40 清理 14 天前的旧备份"
else
  echo "   这台机器没装 cron，跳过定时备份（手动跑：cd $DIR && python3 app.py --backup）"
fi

sleep 2
echo "⑦ 结果："
systemctl --no-pager -l status tianshu | head -6 || true
echo
curl -s -o /dev/null -w "   本机自测 http://127.0.0.1:$PORT → HTTP %{http_code}\n" "http://127.0.0.1:$PORT/" || true
echo
echo "=============================================="
echo "✅ 服务器这边装好了。还差最后一步（在阿里云控制台点）："
echo
echo "  在域名 DNS 加一条 A 记录："
echo "    主机记录  $(echo "$DOMAIN" | cut -d. -f1)"
echo "    记录类型  A"
echo "    记录值    这台服务器的公网 IP"
echo
echo "  等几分钟，然后手机流量打开：https://$DOMAIN"
echo "  （证书是 Caddy 自动申请的，第一次打开可能要等 10 秒）"
echo
echo "  以后更新网站：本机 git push → 服务器上再跑一次这条命令即可"
echo "=============================================="
