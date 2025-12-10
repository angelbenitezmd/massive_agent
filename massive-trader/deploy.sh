#!/bin/bash
set -e

echo "=== Massive Trader Deployment Script ==="
echo ""

# Step 1: Add swap if not exists
if [ ! -f /swapfile ]; then
    echo "[1/6] Creating 2GB swap file..."
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "Swap created."
else
    echo "[1/6] Swap already exists, skipping..."
fi

# Step 2: Install Docker if not installed
if ! command -v docker &> /dev/null; then
    echo "[2/6] Installing Docker..."
    apt-get update
    apt-get install -y docker.io docker-compose
    systemctl start docker
    systemctl enable docker
else
    echo "[2/6] Docker already installed."
fi

# Step 3: Open firewall ports
echo "[3/6] Configuring firewall..."
ufw allow 22/tcp
ufw allow 3000/tcp
ufw allow 8000/tcp
ufw --force enable

# Step 4: Check for .env file
echo "[4/6] Checking environment..."
if [ ! -f .env ]; then
    echo ""
    echo "ERROR: .env file not found!"
    echo "Create .env with your API keys:"
    echo ""
    echo "  ALPACA_API_KEY_ID=your_key"
    echo "  ALPACA_API_SECRET_KEY=your_secret"
    echo "  BENZINGA_API_KEY=your_key"
    echo "  ANTHROPIC_API_KEY=your_key"
    echo "  NEXT_PUBLIC_API_URL=http://YOUR_DROPLET_IP:8000"
    echo ""
    exit 1
fi

# Step 5: Stop existing containers
echo "[5/6] Stopping existing containers..."
docker-compose down 2>/dev/null || true

# Step 6: Build and start (one at a time to save memory)
echo "[6/6] Building and starting services..."
echo ""
echo "Building backend..."
docker-compose build backend
echo ""
echo "Starting backend..."
docker-compose up -d backend
echo "Waiting for backend to be ready..."
sleep 10

echo ""
echo "Building frontend..."
docker-compose build frontend
echo ""
echo "Starting frontend..."
docker-compose up -d frontend

echo ""
echo "=== Deployment Complete ==="
echo ""
docker ps
echo ""
echo "Backend:  http://$(curl -s ifconfig.me):8000/status"
echo "Frontend: http://$(curl -s ifconfig.me):3000"
echo ""
