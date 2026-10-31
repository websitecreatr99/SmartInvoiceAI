#!/usr/bin/env bash
# One-time setup on a fresh Oracle Cloud Ubuntu 22.04/24.04 VM, then (re)deploy.
#   curl -fsSL https://raw.githubusercontent.com/kishannextq/hackathon/infra/oracle/setup.sh | bash
# Re-run it any time to pull the latest code on every branch and rebuild.
set -euo pipefail

REPO="${REPO:-https://github.com/kishannextq/hackathon.git}"
ROOT="${ROOT:-$HOME/invoiceai}"

if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi

# Oracle's Ubuntu images REJECT everything but SSH in iptables, on top of the VCN security list.
if ! sudo iptables -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null; then
  sudo iptables -I INPUT 6 -p tcp --dport 80 -j ACCEPT
  sudo iptables -I INPUT 6 -p tcp --dport 443 -j ACCEPT
  sudo apt-get install -y iptables-persistent >/dev/null
  sudo netfilter-persistent save
fi

clone() {  # clone <branch> <dir>
  if [ -d "$ROOT/$2/.git" ]; then
    git -C "$ROOT/$2" pull --ff-only
  else
    git clone --depth 1 --branch "$1" "$REPO" "$ROOT/$2"
  fi
}
mkdir -p "$ROOT"
clone fastapi api
clone worker worker
clone frontend frontend
clone infra infra

cd "$ROOT/infra/oracle"
if [ ! -f .env ]; then
  cp .env.example .env
  sed -i "s/^RABBITMQ_PASSWORD=.*/RABBITMQ_PASSWORD=$(openssl rand -hex 16)/" .env
  ip=$(curl -fsS https://ifconfig.me || true)
  [ -n "$ip" ] && sed -i "s/^DOMAIN=.*/DOMAIN=${ip//./-}.sslip.io/" .env
fi

if ! grep -q '^GOOGLE_API_KEY=.\+' .env; then
  echo "Put your Gemini key in $ROOT/infra/oracle/.env (GOOGLE_API_KEY=...), then run this script again."
  exit 1
fi

sudo docker compose up -d --build
sudo docker compose ps
echo "Up at https://$(grep '^DOMAIN=' .env | cut -d= -f2)"
