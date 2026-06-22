# WC on gx10 — phone SSH cheat sheet

Connect via Tailscale: `ssh mauber@gx10` (or `ssh spark` from Mac).

Project path: `~/WC`

## Every session

```bash
export PATH="$HOME/.local/bin:$PATH"
cd ~/WC
```

## App (ports 5180 / 8000)

```bash
curl -s http://127.0.0.1:8000/api/v1/health          # up?

nohup env WC_WEB_PORT=5180 WC_API_PORT=8000 make dev-remote > /tmp/wc-dev.log 2>&1 &

tail -f /tmp/wc-dev.log
```

Port 5180 avoids conflict with agent-dashboard on 5173.

## UI on your phone

In Termius / Blink, forward **both** ports:

| Local | Remote |
|-------|--------|
| 5180 | 127.0.0.1:5180 |
| 8000 | 127.0.0.1:8000 |

Open **http://localhost:5180** in the phone browser.

## Code updates

```bash
cd ~/WC && git pull && make setup && make migrate
```

First time on Spark: `git clone https://github.com/mauber91/WC.git ~/WC`

From Mac (not phone): `make spark-sync`

## Data sync

```bash
make refresh-tournament
make sync-markets
make sync-markets -- --match-number 33
make squad-data
make seed-data
```

Admin API (set `WC_ADMIN_API_KEY` in `.env`):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/admin/tournament/refresh -H "X-Admin-Key: $WC_ADMIN_API_KEY"
curl -X POST http://127.0.0.1:8000/api/v1/admin/markets/sync -H "X-Admin-Key: $WC_ADMIN_API_KEY"
```

## Simulations

```bash
curl -X POST http://127.0.0.1:8000/api/v1/simulations \
  -H 'Content-Type: application/json' \
  -d '{"iterations": 50000, "seed": 42}'

curl http://127.0.0.1:8000/api/v1/simulations
make benchmark
```

Tune workers in `.env`: `WC_SIMULATION_MAX_WORKERS=6` (raise on Spark).

## Publish & deploy

On Spark:

```bash
make publish ARGS="..."
```

From Mac only (needs `fly` / `wrangler` auth):

```bash
make deploy-fly ARGS="--app ... --cors-origin ..."
make deploy-pages ARGS="..."
```

## Mac-only helpers

```bash
make spark-sync      # rsync code → gx10
make spark-start     # start dev servers on gx10
make spark-tunnel    # forward 5180 + 8000 to Mac
```
