# Sigmo – Roadmap & Planned Improvements

This document tracks known improvements and future phases for the Sigmo platform.

---

## Phase 2 – Monitoring & Observability Hardening

### Grafana Secure Public Access

**Current state:** Grafana is accessible at `http://<server-ip>:4000` — IP and port only, HTTP, admin-facing.

**Planned improvement:** Route Grafana through the existing Nginx reverse proxy so it is served over HTTPS with no extra ports exposed publicly. Two options under consideration:

- **Subpath** – `https://tg.yourdomain.com/grafana`
  - Reuses the existing SSL certificate
  - No new DNS record needed
  - Requires `GF_SERVER_ROOT_URL` and `GF_SERVER_SERVE_FROM_SUB_PATH=true` in Grafana config
  - One new `location /grafana` block in `nginx.conf`

- **Subdomain** – `https://grafana.yourdomain.com`
  - Cleaner URL and fully isolated
  - Requires a new DNS A record pointing to the same VPS IP
  - Requires a second SSL certificate via Certbot
  - New `server` block in `nginx.conf`

The subpath approach is preferred as it requires no new DNS configuration and reuses the existing cert.

**Until this is implemented:** Keep port `4000` firewalled to admin IPs only. Do not expose it to the public internet without authentication hardening.

---

## Phase 3 – Alerting

**Planned:** Set up Prometheus alerting rules with Alertmanager to notify admins via Telegram when:

- CPU usage exceeds 85% for more than 5 minutes
- Disk usage exceeds 90%
- The FastAPI container stops responding to `/health`
- A restaurant has not started any checklist by a configurable deadline

---

## Phase 4 – Log Aggregation

**Planned:** Add Grafana Loki + Promtail to collect and query container logs (FastAPI, Nginx, Postgres) directly from the Grafana dashboards, removing the need to SSH in to check logs.

---

## Phase 5 – Multi-Branch Scaling

**Planned:** Evaluate whether the current single-instance deployment is sufficient as more restaurants and branches are onboarded, or whether horizontal scaling and a load balancer are needed.
