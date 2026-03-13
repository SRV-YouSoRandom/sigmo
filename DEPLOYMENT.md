# Sigmo – Deployment Guide

## Overview

```mermaid
graph TD
    subgraph Server["Ubuntu VPS"]
        NX[Nginx :80/:443] --> FA[FastAPI :8000]
        FA --> PB[PgBouncer :5432]
        PB --> PG[(PostgreSQL :5432)]
        FA -->|Cron 08:00| SCH[APScheduler]
        PROM[Prometheus :9090] --> FA
        GR[Grafana :3000] --> PROM
    end
    TG[Telegram API] <-->|Webhook| NX
```

---

## Prerequisites

- Ubuntu 22.04+ VPS with a public IP
- Domain name with an A record pointing to your VPS IP (e.g. `tg.yourdomain.com`)
- Docker Engine 24+ and Docker Compose v2
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

---

## 1. Server Setup

```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
sudo apt install docker-compose-plugin -y
docker compose version
```

---

## 2. SSL Certificate

Stop Nginx before running certbot so port 80 is free:

```bash
docker compose -f docker-compose.prod.yml stop nginx
sudo apt install certbot -y
sudo certbot certonly --standalone -d tg.yourdomain.com
```

Certificates are stored at:

- `/etc/letsencrypt/live/tg.yourdomain.com/fullchain.pem`
- `/etc/letsencrypt/live/tg.yourdomain.com/privkey.pem`

Update nginx.conf with your actual domain:

```bash
sed -i 's/yourdomain.com/tg.yourdomain.com/g' docker/nginx.conf
```

---

## 3. Clone & Configure

```bash
git clone https://github.com/SRV-YouSoRandom/sigmo.git
cd sigmo
cp .env.example .env
nano .env
```

Fill in required values:

```env
TELEGRAM_BOT_TOKEN=<token from BotFather>
POSTGRES_HOST=pgbouncer
POSTGRES_PORT=5432
POSTGRES_DB=sigmo
POSTGRES_USER=sigmo
POSTGRES_PASSWORD=<strong random password>
SECRET_WEBHOOK_PATH=/webhook
ENVIRONMENT=production
LOG_LEVEL=INFO
```

> Note: PgBouncer listens on port 5432 in this setup, not 6432.

---

## 4. PgBouncer Auth Fix

The `edoburu/pgbouncer` image must use `scram-sha-256` to match asyncpg. Make sure your `docker-compose.prod.yml` pgbouncer service includes:

```yaml
pgbouncer:
  image: edoburu/pgbouncer
  environment:
    DB_HOST: postgres
    DB_NAME: sigmo
    DB_USER: sigmo
    DB_PASSWORD: ${POSTGRES_PASSWORD}
    AUTH_TYPE: scram-sha-256
  depends_on:
    - postgres
  restart: always
```

---

## 5. Deploy

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

---

## 6. Run Migrations

Alembic must connect directly to Postgres, not PgBouncer:

```bash
# Generate migration files
docker compose -f docker-compose.prod.yml exec fastapi sh -c \
  "POSTGRES_HOST=postgres POSTGRES_PORT=5432 alembic revision --autogenerate -m 'initial'"

# Apply migrations
docker compose -f docker-compose.prod.yml exec fastapi sh -c \
  "POSTGRES_HOST=postgres POSTGRES_PORT=5432 alembic upgrade head"

# Verify tables
docker compose -f docker-compose.prod.yml exec postgres psql -U sigmo -d sigmo -c "\dt"
```

---

## 7. Register Telegram Webhook

```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -d "url=https://tg.yourdomain.com/webhook"
# Expected: {"ok":true,"result":true,"description":"Webhook was set"}
```

---

## 8. Verify Health

```bash
curl https://tg.yourdomain.com/health
# Expected: {"status":"ok","database":true}
```

---

## 9. Seed Data

Connect to Postgres:

```bash
docker compose -f docker-compose.prod.yml exec postgres psql -U sigmo -d sigmo
```

> To find a Telegram chat_id, have the user message [@userinfobot](https://t.me/userinfobot) on Telegram.

```sql
-- Add restaurant
INSERT INTO restaurants (restaurant_id, name, manager_chat_id)
VALUES ('R001', 'My Restaurant', '<manager_telegram_chat_id>');

-- Add staff (repeat for each staff member)
INSERT INTO staff (chat_id, name, restaurant_id)
VALUES ('<staff_telegram_chat_id>', 'Staff Name', 'R001');

-- Sample checklist steps (first 5 of Dining Opening)
-- Step 9 and 11 require a photo as an example
INSERT INTO checklist_steps (restaurant_id, checklist_id, step_number, instruction, requires_photo) VALUES
('R001', 'DINING_OPEN', 1, 'Turn on lights', false),
('R001', 'DINING_OPEN', 2, 'Turn on AC', false),
('R001', 'DINING_OPEN', 3, 'Turn on sounds', false),
('R001', 'DINING_OPEN', 4, 'Turn on POS and let it boot', false),
('R001', 'DINING_OPEN', 5, 'Read endorsements if any', false);
-- ... add remaining steps as needed
```

---

## 10. Bring Nginx Back Up

```bash
docker compose -f docker-compose.prod.yml up -d nginx
```

---

## 11. Operations

### View Logs

```bash
docker compose -f docker-compose.prod.yml logs -f fastapi
docker compose -f docker-compose.prod.yml logs -f postgres
```

### Restart Services

```bash
docker compose -f docker-compose.prod.yml restart
```

### Update Code

```bash
cd /opt/sigmo
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec fastapi sh -c \
  "POSTGRES_HOST=postgres POSTGRES_PORT=5432 alembic upgrade head"
```

### Monitoring

| Service    | URL                                | Access     |
| ---------- | ---------------------------------- | ---------- |
| Health     | `https://tg.yourdomain.com/health` | Public     |
| Prometheus | `http://server-ip:9090`            | SSH tunnel |
| Grafana    | `http://server-ip:3000`            | SSH tunnel |

To access Grafana or Prometheus locally via SSH tunnel:

```bash
ssh -L 3000:localhost:3000 user@your-vps-ip
# Then open http://localhost:3000 in your browser
```

---

## 12. Backup

```bash
docker compose -f docker-compose.prod.yml exec postgres pg_dump -U sigmo sigmo > backup_$(date +%F).sql
```

Restore:

```bash
cat backup_2026-03-13.sql | docker compose -f docker-compose.prod.yml exec -T postgres psql -U sigmo sigmo
```

---

## 13. Troubleshooting

| Symptom                     | Check                                                                          |
| --------------------------- | ------------------------------------------------------------------------------ |
| Bot not responding          | `docker compose logs fastapi` – verify bot token and webhook                   |
| `database: false` in health | Check PgBouncer AUTH_TYPE is `scram-sha-256`, verify POSTGRES_PASSWORD matches |
| Alembic connection refused  | Run with `POSTGRES_HOST=postgres POSTGRES_PORT=5432` to bypass PgBouncer       |
| Nginx restarting            | SSL certs missing – run certbot before starting Nginx                          |
| Webhook 404                 | Make sure full token is included: `bot<id>:<hash>`                             |
| No daily summary            | Verify `manager_chat_id` is correct in restaurants table                       |
