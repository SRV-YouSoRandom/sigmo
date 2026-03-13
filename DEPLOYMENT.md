# Sigmo – Deployment Guide

## Prerequisites

- Ubuntu 22.04+ VPS with a public IP
- Domain name with an A record pointing to your VPS IP
- Docker Engine 24+ and Docker Compose v2
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

---

## 1. Server Setup

```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
sudo apt install docker-compose-plugin -y
```

---

## 2. SSL Certificate

```bash
sudo apt install certbot -y
sudo certbot certonly --standalone -d tg.yourdomain.com
```

Certificates will be at:

- `/etc/letsencrypt/live/tg.yourdomain.com/fullchain.pem`
- `/etc/letsencrypt/live/tg.yourdomain.com/privkey.pem`

---

## 3. Clone & Configure

```bash
git clone https://github.com/SRV-YouSoRandom/sigmo.git
cd sigmo
cp .env.example .env
nano .env
```

Fill in:

```env
TELEGRAM_BOT_TOKEN=<token from BotFather>
POSTGRES_PASSWORD=<strong random password>
```

Update nginx.conf with your domain:

```bash
sed -i 's/yourdomain.com/tg.yourdomain.com/g' docker/nginx.conf
```

---

## 4. Deploy

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

---

## 5. Run Migrations

```bash
# Generate
docker compose -f docker-compose.prod.yml exec fastapi sh -c \
  "POSTGRES_HOST=postgres POSTGRES_PORT=5432 alembic revision --autogenerate -m 'initial'"

# Apply
docker compose -f docker-compose.prod.yml exec fastapi sh -c \
  "POSTGRES_HOST=postgres POSTGRES_PORT=5432 alembic upgrade head"
```

---

## 6. Seed Data

Connect to Postgres:

```bash
docker compose -f docker-compose.prod.yml exec postgres psql -U sigmo -d sigmo
```

> To find a Telegram chat_id, have the user message [@userinfobot](https://t.me/userinfobot).

```sql
-- Restaurant
INSERT INTO restaurants (restaurant_id, name, manager_chat_id)
VALUES ('R001', 'My Restaurant', '<manager_telegram_chat_id>');

-- Manager (gives manager UI in the bot)
INSERT INTO managers (chat_id, name, restaurant_id)
VALUES ('<manager_telegram_chat_id>', 'Manager Name', 'R001');

-- Staff (repeat for each staff member)
INSERT INTO staff (chat_id, name, restaurant_id)
VALUES ('<staff_telegram_chat_id>', 'Staff Name', 'R001');

-- Checklist steps (see seedsqlcmds.md for full step lists)
```

Type `\q` to exit.

---

## 7. Register Telegram Webhook

```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -d "url=https://tg.yourdomain.com/webhook"
# Expected: {"ok":true,"result":true}
```

---

## 8. Verify

```bash
curl https://tg.yourdomain.com/health
# Expected: {"status":"ok","database":true}
```

---

## Operations

### View Logs

```bash
docker compose -f docker-compose.prod.yml logs -f fastapi
```

### Restart

```bash
docker compose -f docker-compose.prod.yml restart
```

### Update Code

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec fastapi sh -c \
  "POSTGRES_HOST=postgres POSTGRES_PORT=5432 alembic upgrade head"
```

### Backup & Restore

```bash
# Backup
docker compose -f docker-compose.prod.yml exec postgres pg_dump -U sigmo sigmo > backup_$(date +%F).sql

# Restore
cat backup.sql | docker compose -f docker-compose.prod.yml exec -T postgres psql -U sigmo sigmo
```

### Reset Database (fresh start)

```bash
docker compose -f docker-compose.prod.yml down
docker volume rm sigmo_pgdata
rm -f migrations/versions/*.py && touch migrations/versions/.gitkeep
docker compose -f docker-compose.prod.yml up -d --build
# Then re-run steps 5 → 8
```

### Monitoring

| Service    | URL                                | Access     |
| ---------- | ---------------------------------- | ---------- |
| Health     | `https://tg.yourdomain.com/health` | Public     |
| Prometheus | `http://server-ip:9090`            | SSH tunnel |
| Grafana    | `http://server-ip:3000`            | SSH tunnel |

```bash
# SSH tunnel example
ssh -L 3000:localhost:3000 user@your-vps-ip
```
