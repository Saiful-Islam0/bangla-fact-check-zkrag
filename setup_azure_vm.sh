#!/usr/bin/env bash
# ==============================================================================
# Setup script for deploying ZK-RAG Fake News Detection on an Azure Ubuntu VM
# Tested on: Ubuntu 22.04 LTS & Ubuntu 24.04 LTS
# ==============================================================================

set -euo pipefail

echo "=========================================================="
echo "🚀 Initializing Azure VM for ZK-RAG Fact Checking System"
echo "=========================================================="

if [ "$EUID" -ne 0 ]; then
  echo "❌ Please run this script with sudo: sudo ./setup_azure_vm.sh"
  exit 1
fi

CURRENT_USER="${SUDO_USER:-$(whoami)}"

echo "==> 1. Updating APT repositories and packages..."
apt-get update -y
apt-get upgrade -y
apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    ufw \
    htop

echo "==> 2. Setting up 4GB Swap Space (essential for PyTorch & OCR on VMs)..."
if [ ! -f /swapfile ]; then
    fallocate -l 4G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=4096
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    if ! grep -q '/swapfile' /etc/fstab; then
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
    fi
    echo "✅ 4GB swapfile successfully enabled."
else
    echo "ℹ️  Swapfile already exists. Skipping."
fi

echo "==> 3. Installing Docker Engine and Docker Compose..."
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable docker
systemctl start docker

# Add non-root user to docker group
if [ "$CURRENT_USER" != "root" ]; then
    usermod -aG docker "$CURRENT_USER"
    echo "✅ Added user $CURRENT_USER to docker group."
fi

echo "==> 4. Configuring Firewall (UFW) for Web & SSH access..."
ufw allow OpenSSH
ufw allow 80/tcp comment 'HTTP Web UI'
ufw allow 443/tcp comment 'HTTPS Web UI'
ufw allow 8000/tcp comment 'FastAPI Backend'
ufw --force enable || true

echo "=========================================================="
echo "🎉 Azure VM Environment Ready!"
echo "Docker Version: $(docker --version)"
echo "Docker Compose Version: $(docker compose version)"
echo "Memory & Swap:"
free -h
echo "=========================================================="
echo "Next Steps:"
echo "1. Run: newgrp docker (or log out and log back in to apply docker group)"
echo "2. Ensure your .env file is filled in with your API keys"
echo "3. Launch the complete application stack:"
echo "   docker compose up --build -d"
echo "4. Access the web interface at: http://<YOUR_AZURE_VM_PUBLIC_IP>"
echo "=========================================================="
