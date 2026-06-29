# Lightsail deployment (single 2 GB box)

Runs the whole app — API, MCP (subprocess of the API), Postgres, Redis, and the
Nginx frontend — as containers on one Lightsail instance. Served over HTTP on
port 80 (IP-only). Cost: ~$12/mo (the 2 GB `small_3_1` plan).

## One-time setup

Instance, ports, static IP, Docker, and swap are already provisioned (see the
project deploy notes). The static IP is the server's permanent address.

## Deploy / update

From your Mac, sync the source to the box (excludes heavy/local dirs):

```bash
rsync -avz --delete \
  --exclude '.git' --exclude 'node_modules' --exclude 'ui/node_modules' \
  --exclude '.venv' --exclude '__pycache__' --exclude '*.db' --exclude '.env' \
  -e "ssh -i ~/wanderbot-lightsail.pem" \
  ~/Desktop/f-p/holiday-planning-system/ ubuntu@<STATIC_IP>:~/wanderbot/
```

Then on the box:

```bash
ssh -i ~/wanderbot-lightsail.pem ubuntu@<STATIC_IP>
cd ~/wanderbot/deploy/lightsail

# First time only: create the secrets file
cp .env.example .env
nano .env            # fill in real keys (see below)

# Build + start (first build takes a few minutes)
docker compose -f docker-compose.prod.yml up -d --build

# Watch it come up
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f app
```

Visit `http://<STATIC_IP>` in a browser.

## Secrets (`.env`)

Lives only on the box, never committed. Generate strong values:

```bash
openssl rand -hex 32   # for POSTGRES_PASSWORD and WB_JWT_SECRET
```

For Bedrock guardrails, the guardrail must exist in `WB_AWS_REGION`, and
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` must belong to an IAM user with
`bedrock:ApplyGuardrail` permission.

## Operations

```bash
# logs
docker compose -f docker-compose.prod.yml logs -f app

# restart one service
docker compose -f docker-compose.prod.yml restart app

# stop everything (stops billing only for compute you can't pause — the
# Lightsail instance itself keeps billing; stop the instance to pause that)
docker compose -f docker-compose.prod.yml down

# memory check
free -h
docker stats --no-stream
```

## Pausing cost

The Lightsail instance bills whether or not containers run. To pause:

```bash
aws lightsail stop-instance --region ap-south-1 --instance-name wanderbot
aws lightsail start-instance --region ap-south-1 --instance-name wanderbot
```

A stopped instance still keeps its disk and static IP (attached static IPs are
free while attached), so you only stop paying for the running compute portion.
