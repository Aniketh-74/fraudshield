#!/bin/bash
# deploy.sh — Run this on the Oracle Cloud VM after SSH in
# Usage: bash deploy.sh
set -e

echo "=== FraudShield Deploy Script ==="

# 1. Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "[1/5] Installing Docker..."
    sudo apt update -y
    sudo apt install -y ca-certificates curl gnupg
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
      | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt update -y
    sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    sudo systemctl enable --now docker
    sudo usermod -aG docker ubuntu
    echo "Docker installed. You may need to log out and back in."
else
    echo "[1/5] Docker already installed — skipping"
fi

# 2. Open firewall ports (Oracle Linux iptables rules)
echo "[2/5] Opening firewall ports..."
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT 2>/dev/null || true
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT 2>/dev/null || true
sudo apt install -y iptables-persistent 2>/dev/null || true
sudo netfilter-persistent save 2>/dev/null || true

# 3. Clone or pull the repo
echo "[3/5] Getting latest code..."
if [ -d "fraudshield" ]; then
    cd fraudshield && git pull
else
    git clone https://github.com/YOUR_GITHUB_USERNAME/fraudshield.git
    cd fraudshield
fi

# 4. Ensure model files exist (copy from training if present)
echo "[4/5] Checking model files..."
if [ ! -f "training/models/calibrated_model.pkl" ]; then
    echo "WARNING: No model file found. ML scorer will run in fallback mode."
    echo "Run 'make train' or copy calibrated_model.pkl to training/models/"
fi

# 5. Start services
echo "[5/5] Starting all services..."
docker compose -f docker-compose.prod.yml pull 2>/dev/null || true
docker compose -f docker-compose.prod.yml up -d --build

echo ""
echo "=== Deploy Complete ==="
echo "Dashboard: http://$(curl -s ifconfig.me)"
echo "Run 'docker compose -f docker-compose.prod.yml logs -f' to watch logs"
