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

echo "① 先做准备（内存小就加 swap），再装系统依赖…"
# 便宜的轻量服务器常见 0.5G 内存 —— 不加 swap 的话 apt/pip 很容易被 OOM 杀掉
MEM_MB=$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 0)
SWAP_MB=$(awk '/SwapTotal/{print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 0)
if [ "$MEM_MB" -lt 1500 ] && [ "$SWAP_MB" -lt 512 ]; then
  if [ ! -f /swapfile ]; then
    fallocate -l 1G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=1024 status=none
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
  fi
  swapon /swapfile 2>/dev/null || true
  grep -q '^/swapfile' /etc/fstab 2>/dev/null || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "   内存 ${MEM_MB}MB，已启用 1G swap（重启也生效）"
else
  echo "   内存 ${MEM_MB}MB / swap ${SWAP_MB}MB，够用，跳过"
fi

# 阿里云的内网镜像（mirrors.cloud.aliyuncs.com）在部分地域 / 轻量机型上很慢甚至直接挂住，
# 让人以为"卡死了"。换成公网镜像，apt 才走得动（2026-09 在香港轻量上踩过）
if grep -rqs 'mirrors.cloud.aliyuncs.com' /etc/apt/sources.list /etc/apt/sources.list.d/ 2>/dev/null; then
  sed -i 's|mirrors.cloud.aliyuncs.com|mirrors.aliyun.com|g' \
    /etc/apt/sources.list /etc/apt/sources.list.d/*.sources 2>/dev/null || true
  echo "   已把 apt 源从内网镜像换成公网镜像 mirrors.aliyun.com"
fi

# 给 apt 上保险（2026-09 在香港轻量上踩过：apt-get update 卡十几分钟、CPU 0:00 = 在网络上干等）：
#   · 强制 IPv4 —— 机器没有 IPv6 路由时，apt 会死等 IPv6 地址
#   · 加超时 —— 卡住就失败，不无限期挂着
#   · 每个 apt 调用外面再套 timeout，"宁可失败也别装死"
cat > /etc/apt/apt.conf.d/99-tianshu <<'APT'
Acquire::ForceIPv4 "true";
Acquire::http::Timeout "20";
Acquire::https::Timeout "20";
Acquire::Retries "2";
APT
rm -f /etc/apt/sources.list.d/caddy-stable.list     # 清掉上次被打断留下的源，它连不上就会拖死 apt

timeout 300 apt-get update -qq || echo "   （apt update 超时或失败，先继续往下试）"
timeout 900 apt-get install -y -qq python3 python3-venv python3-pip git curl gnupg \
  debian-keyring debian-archive-keyring apt-transport-https || true
if ! command -v python3 >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1; then
  echo "   [X] 系统包没装上（apt 连不上镜像）。先把 apt 弄通再重跑本脚本："
  echo "       试试换镜像：sed -i 's|mirrors.aliyun.com|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list /etc/apt/sources.list.d/*.sources"
  exit 1
fi

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
  CADDY_VER="${CADDY_VER:-2.8.4}"
  OK=0
  # 先试官方 apt 源（好处：以后跟系统一起升级）
  # —— 所有下载都带 --connect-timeout/--max-time：境外源连不上时是"失败"而不是"永远卡住"
  if curl -fsSL --connect-timeout 10 --max-time 60 -o /tmp/caddy.key \
       'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' 2>/dev/null; then
    gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg /tmp/caddy.key 2>/dev/null || true
    if curl -fsSL --connect-timeout 10 --max-time 60 -o /etc/apt/sources.list.d/caddy-stable.list \
         'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' 2>/dev/null; then
      timeout 300 apt-get update -qq 2>/dev/null || true
      timeout 600 apt-get install -y -qq caddy 2>/dev/null && OK=1
    fi
  fi
  if [ "$OK" != "1" ]; then
    # 退回 GitHub 单文件版：一样是官方构建，只是不走 apt
    echo "   官方 apt 源连不上，改用 GitHub 上的 Caddy 单文件版…"
    curl -fL --connect-timeout 10 --max-time 240 -o /tmp/caddy.tgz \
      "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VER}/caddy_${CADDY_VER}_linux_amd64.tar.gz"
    tar -xzf /tmp/caddy.tgz -C /usr/local/bin caddy
    chmod +x /usr/local/bin/caddy
    cat > /etc/systemd/system/caddy.service <<'UNIT'
[Unit]
Description=Caddy（单文件版，由 tianshu 部署脚本安装）
After=network.target

[Service]
Type=notify
ExecStart=/usr/local/bin/caddy run --environ --config /etc/caddy/Caddyfile
ExecReload=/usr/local/bin/caddy reload --config /etc/caddy/Caddyfile --force
Restart=on-failure
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload
  fi
  /usr/local/bin/caddy version 2>/dev/null || caddy version || true
fi
mkdir -p /etc/caddy

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
