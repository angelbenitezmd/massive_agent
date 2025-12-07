# Deployment Guide - Signalist AI Trader

## Quick Deploy to Hetzner VPS

### Step 1: Create Hetzner Account & Server
1. Go to https://www.hetzner.com/cloud
2. Create account
3. Create new project → Add Server
4. Choose:
   - **Location**: Ashburn (US) or closest to you
   - **Image**: Ubuntu 24.04
   - **Type**: CX22 ($4.50/mo) - 2 vCPU, 4GB RAM
   - **Add SSH Key** (or use password)
5. Click Create

### Step 2: Connect to Your Server
```bash
ssh root@YOUR_SERVER_IP
```

### Step 3: Install Docker (One-time setup)
```bash
# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh

# Install Docker Compose
apt install docker-compose-plugin -y

# Verify installation
docker --version
docker compose version
```

### Step 4: Deploy the App
```bash
# Clone your repo (or copy files)
git clone https://github.com/YOUR_USERNAME/massive-trader.git
cd massive-trader

# Create .env file with your API keys
cp .env.example .env
nano .env  # Edit and add your real API keys

# Build and start everything
docker compose up -d --build

# Check status
docker compose ps
docker compose logs -f
```

### Step 5: Access Your Dashboard
Open in browser: `http://YOUR_SERVER_IP:3000`

---

## Useful Commands

```bash
# View logs
docker compose logs -f

# Restart services
docker compose restart

# Stop everything
docker compose down

# Update and redeploy
git pull
docker compose up -d --build

# Check resource usage
docker stats
```

---

## Optional: Add Domain & HTTPS

### Using Cloudflare (Free & Easy)
1. Buy domain or use existing one
2. Add site to Cloudflare
3. Create A record: `trader.yourdomain.com` → `YOUR_SERVER_IP`
4. Enable Cloudflare Proxy (orange cloud) - gives you free HTTPS

### Using Caddy (Auto HTTPS)
```bash
# Install Caddy
apt install caddy

# Edit /etc/caddy/Caddyfile
trader.yourdomain.com {
    reverse_proxy localhost:3000
}

# Restart Caddy
systemctl restart caddy
```

---

## Optional: Password Protection

Add basic auth to your frontend. Edit `docker-compose.yml`:

```yaml
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./.htpasswd:/etc/nginx/.htpasswd
    depends_on:
      - frontend
```

Create `.htpasswd`:
```bash
apt install apache2-utils
htpasswd -c .htpasswd admin  # Creates user "admin"
```

---

## Costs Summary

| Service | Cost |
|---------|------|
| Hetzner CX22 | $4.50/mo |
| Domain (optional) | $10-15/yr |
| **Total** | **~$5/mo** |

---

## Troubleshooting

### App not starting?
```bash
docker compose logs backend
docker compose logs frontend
```

### Port already in use?
```bash
# Find what's using port 3000
lsof -i :3000
# Kill it
kill -9 PID
```

### Out of memory?
```bash
# Check memory
free -h
# Add swap
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
```
