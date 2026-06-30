# Roam — Operations Runbook (AWS Lightsail)

Everything you need to operate the deployed app: connect, start/stop, manage
secrets, deploy, manage CI/CD, and tear it all down.

## Your setup at a glance

| Thing | Value |
|---|---|
| Instance name | `wanderbot` |
| Region | `ap-south-1` (Mumbai) |
| Plan | `small_3_1` (2 GB RAM) — **~$12/month, flat** |
| Static IP | `13.206.150.1` (named `wanderbot-ip`) |
| Domain | `https://roamtrips.duckdns.org` |
| SSH key (on your Mac) | `~/wanderbot-lightsail.pem` |
| Login user | `ubuntu` |
| App folder (on server) | `~/wanderbot` |
| Compose file (on server) | `~/wanderbot/deploy/lightsail/docker-compose.prod.yml` |
| Secrets file (on server) | `~/wanderbot/deploy/lightsail/.env` |
| GitHub repo | `cse18107/wander-bot` |

A note on cost up front: **Lightsail bills a flat monthly price for the plan
whether the instance is running or stopped.** Stopping it is only for rebooting
the OS — it does **not** save money. The only way to stop paying is to
**delete** the instance (see "Delete the whole service").

---

## 1. Connect to the server (from scratch)

All admin happens over SSH from your Mac's terminal.

```bash
ssh -i ~/wanderbot-lightsail.pem ubuntu@13.206.150.1
```

You'll land at a prompt like `ubuntu@ip-172-26-5-104:~$`. That's the server.
Type `exit` to disconnect and return to your Mac.

If you ever lose the key file, you can re-download it:

```bash
aws lightsail download-default-key-pair --region ap-south-1 \
  --query privateKeyBase64 --output text > ~/wanderbot-lightsail.pem
chmod 600 ~/wanderbot-lightsail.pem
```

You can also use the **browser SSH**: AWS Console → Lightsail → instance
`wanderbot` → "Connect using SSH". No key needed.

---

## 2. Check / start / stop / reboot the instance

These are run **on your Mac** (they use the AWS CLI, not SSH).

Check current state:

```bash
aws lightsail get-instance-state --region ap-south-1 --instance-name wanderbot
```

Stop (powers the box off — **billing continues**, this is just a power-off):

```bash
aws lightsail stop-instance --region ap-south-1 --instance-name wanderbot
```

Start again:

```bash
aws lightsail start-instance --region ap-south-1 --instance-name wanderbot
```

Reboot (stop + start in one go):

```bash
aws lightsail reboot-instance --region ap-south-1 --instance-name wanderbot
```

The static IP and disk are kept across stop/start, so the app comes back at the
same address. After a start, the containers auto-launch (they're set to
`restart: unless-stopped`), so the app returns on its own in ~1 minute.

---

## 3. Manage the running app (containers)

SSH in first, then move to the deploy folder:

```bash
ssh -i ~/wanderbot-lightsail.pem ubuntu@13.206.150.1
cd ~/wanderbot/deploy/lightsail
```

All commands below use `docker compose -f docker-compose.prod.yml`:

```bash
# status of all 5 containers (caddy, web, app, postgres, redis)
docker compose -f docker-compose.prod.yml ps

# live logs for the API (Ctrl+C to stop watching)
docker compose -f docker-compose.prod.yml logs app -f

# logs for HTTPS / Caddy, or the frontend
docker compose -f docker-compose.prod.yml logs caddy --tail 50
docker compose -f docker-compose.prod.yml logs web --tail 50

# restart one service
docker compose -f docker-compose.prod.yml restart app

# stop the whole app stack (containers only; instance stays up)
docker compose -f docker-compose.prod.yml down

# start it back up
docker compose -f docker-compose.prod.yml up -d

# memory check (handy on the 2 GB box)
free -h
docker stats --no-stream
```

---

## 4. Environment variables (`.env`)

All secrets and config live in **one file on the server**:
`~/wanderbot/deploy/lightsail/.env`. It is **never** in Git. Editing it is how
you change API keys, the LLM model, the guardrail ID, etc.

### View current variables

```bash
ssh -i ~/wanderbot-lightsail.pem ubuntu@13.206.150.1
cd ~/wanderbot/deploy/lightsail
cat .env
```

### Add / edit / delete a variable

Open it in the `nano` editor:

```bash
nano .env
```

- **Add**: go to a new line and type `WB_SOMETHING=value`.
- **Edit**: move the cursor to the value and change it.
- **Delete**: put the cursor on the line and press `Ctrl+K` to cut the whole line.

Save and exit nano: `Ctrl+O`, then `Enter`, then `Ctrl+X`.

### Apply the change (required!)

Changes to `.env` only take effect after the app container is **recreated**:

```bash
docker compose -f docker-compose.prod.yml up -d --force-recreate app
```

If you changed something the frontend or proxy uses, recreate everything:

```bash
docker compose -f docker-compose.prod.yml up -d --force-recreate
```

### What the key variables mean

```
POSTGRES_PASSWORD          # database password (used by Postgres + the app)
WB_JWT_SECRET              # signs user login tokens
WB_LLM_PROVIDER            # openai | gemini
WB_LLM_MODEL               # e.g. gemini-2.5-flash
WB_OPENAI_API_KEY          # OpenAI key (if provider=openai)
WB_GOOGLE_API_KEY          # Gemini key (if provider=gemini)
WB_DUFFEL_API_KEY          # flights
WB_TAVILY_API_KEY          # web search + images
WB_GUARDRAILS_BACKEND      # bedrock | regex
WB_BEDROCK_GUARDRAIL_ID    # the guardrail to enforce
WB_AWS_REGION              # region the guardrail lives in
AWS_ACCESS_KEY_ID          # IAM creds for Bedrock (ApplyGuardrail)
AWS_SECRET_ACCESS_KEY
```

> Caution: never commit `.env`, and rotate any key you've ever pasted in chat.

---

## 5. Deploy changes

### Automatic (normal path)

Just push to `main`. GitHub Actions builds + restarts on the server.

```bash
git checkout main && git pull origin main
# ...make edits...
git add -A && git commit -m "describe change"
git push origin main
```

Watch it at: GitHub → repo → **Actions → CD**. ~3–5 min, then live.

### Manual deploy (on the server)

If you edited files directly on the box, or want to rebuild without a push:

```bash
cd ~/wanderbot/deploy/lightsail
docker compose -f docker-compose.prod.yml up -d --build
```

---

## 6. Manage GitHub Actions (CI/CD)

### The two workflows

- **CI** (`.github/workflows/ci.yml`) — lint/type/test + frontend build. Advisory
  (won't block).
- **CD** (`.github/workflows/deploy.yml`) — deploys to Lightsail on every push to
  `main`.

### Secrets CD needs (already set)

GitHub → repo → **Settings → Secrets and variables → Actions**:

- `LIGHTSAIL_SSH_KEY` — full contents of `~/wanderbot-lightsail.pem`
- `LIGHTSAIL_HOST` — `13.206.150.1`

To update one (e.g. after changing the server IP), click the secret → **Update**.

### Trigger a deploy manually

GitHub → **Actions → CD → Run workflow → Run**. (Works because the workflow has
`workflow_dispatch`.)

### Pause / resume auto-deploy

To stop deploying on every push: GitHub → **Actions → CD →** the `···` menu →
**Disable workflow**. Re-enable the same way. (Or comment out the `push:` trigger
in `deploy.yml` and push that change.)

### Re-run or inspect a run

Click any run under **Actions**. Use **Re-run jobs** to retry a failed deploy;
expand a step to read its logs.

### Turn CI back into a hard gate (later)

When you do the lint cleanup, remove the `continue-on-error: true` lines from the
`quality` job in `ci.yml` so failures block again.

---

## 7. Delete the whole service from AWS (full teardown)

Do this when you want to **stop paying entirely**. Order matters.

```bash
# 1. Delete the Lightsail instance (stops the ~$12/mo charge)
aws lightsail delete-instance --region ap-south-1 --instance-name wanderbot

# 2. Release the static IP (an UNattached static IP costs a small hourly fee)
aws lightsail release-static-ip --region ap-south-1 --static-ip-name wanderbot-ip

# 3. (Optional) Delete the Bedrock guardrail
aws bedrock delete-guardrail --region ap-south-1 \
  --guardrail-identifier <YOUR_GUARDRAIL_ID>
```

Then clean up the bits outside AWS:

- **DuckDNS**: log in at duckdns.org and delete the `roamtrips` domain (or just
  leave it — it's free).
- **GitHub**: optionally delete the `LIGHTSAIL_SSH_KEY` / `LIGHTSAIL_HOST` secrets
  and disable the CD workflow so it stops trying to deploy.
- **IAM**: if you created an access key just for Bedrock, deactivate/delete it in
  the IAM console.

Verify nothing is left billing:

```bash
aws lightsail get-instances --region ap-south-1 --query "instances[].name"
aws lightsail get-static-ips --region ap-south-1 --query "staticIps[].name"
```

Both should return an empty list.

> Deleting the instance destroys its disk — including the Postgres data (users,
> saved plans). Export anything you want to keep first.

---

## 8. Quick reference

```bash
# connect
ssh -i ~/wanderbot-lightsail.pem ubuntu@13.206.150.1

# instance power (billing continues while stopped)
aws lightsail stop-instance  --region ap-south-1 --instance-name wanderbot
aws lightsail start-instance --region ap-south-1 --instance-name wanderbot

# app control (on the server, in ~/wanderbot/deploy/lightsail)
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs app -f
docker compose -f docker-compose.prod.yml up -d --force-recreate app   # after .env edit
docker compose -f docker-compose.prod.yml up -d --build                # rebuild

# deploy
git push origin main        # auto-deploys via GitHub Actions

# stop paying entirely
aws lightsail delete-instance   --region ap-south-1 --instance-name wanderbot
aws lightsail release-static-ip --region ap-south-1 --static-ip-name wanderbot-ip
```
