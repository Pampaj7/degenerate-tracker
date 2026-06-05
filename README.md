# DegenerateTracker Analytics

Internal League of Legends analytics for opted-in Discord users. The app runs a `discord.py` slash-command bot, polls the official Riot Games API, stores data in SQLite, and serves a private Plotly Dash dashboard.

The real mission is simple: help my friends stop playing League of Legends by making the damage visible. DegenerateTracker turns Discord into a friendly intervention machine: it tracks how much time everyone spends in LoL, shows daily and weekly stats, and keeps a live leaderboard of the most degenerate grinders in the server.

It is meant to be funny, mildly shameful, and actually useful. Nobody is tracked without opting in, but once they do, the bot makes it very hard to pretend that "one quick game" did not become six hours and a ranked spiral.

## What It Does

- `/optin`, `/optout`, and `/delete_my_data` give users explicit control over tracking.
- `/lol_link game_name tag_line` resolves a Riot ID to PUUID through Account-V1.
- A background poller stores recent Match-V5 matches and League-V4 ranked snapshots.
- Discord presence updates store League of Legends play sessions for opted-in users.
- `/leaderboard` ranks the server by games, winrate, LP movement, and playtime so everyone can see who is currently the most degenerate.
- `/roast` adds a light Discord roast based on recent stats.
- The dashboard exposes server overview, player profile, player comparison, and champion analytics pages.

SQLite is used initially through a small database wrapper. That keeps the first deployment simple while leaving room to replace the persistence layer with Postgres later.

## Discord Setup

1. Create an application at <https://discord.com/developers/applications>.
2. Add a bot user and copy the bot token into `.env` as `DISCORD_TOKEN`.
3. In the bot settings, enable `Presence Intent`. The app also uses guild/member data for slash commands and display names.
4. Invite the bot with scopes `bot` and `applications.commands`.
5. For faster slash-command registration during development, set `GUILD_ID` to your Discord server ID.

Never commit `.env`. Tokens are read from environment variables and are not logged.

## Riot API Setup

1. Create a developer account at <https://developer.riotgames.com/>.
2. Generate an API key and set `RIOT_API_KEY` in `.env`.
3. Use `RIOT_REGION_CLUSTER=europe` and `RIOT_PLATFORM_ROUTING=euw1` for EUW by default.

Riot development API keys expire. If linking or polling starts returning 403, generate a fresh key.

## Environment

Copy the example file:

```bash
cp .env.example .env
```

Required:

- `DISCORD_TOKEN`
- `RIOT_API_KEY`

Optional:

- `GUILD_ID`
- `RIOT_REGION_CLUSTER`, default `europe`
- `RIOT_PLATFORM_ROUTING`, default `euw1`
- `POLL_INTERVAL_SECONDS`, default `300`
- `DASH_HOST`, default `0.0.0.0`
- `DASH_PORT`, default `8050`
- `PUBLIC_DASHBOARD_URL`

If `PUBLIC_DASHBOARD_URL` is unset, `/lol_dashboard` returns `http://localhost:DASH_PORT`. That only works from the machine running the app.

## Local Run

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

The SQLite database is created at `data/degenerate_tracker.sqlite`.

## Docker Compose

```bash
docker compose up -d --build
docker compose logs -f
```

The single service runs both the Discord bot and Dash dashboard in one Python process. This is the simplest stable initial deployment. If the dashboard or poller grows heavy, split them into separate services that share the same SQLite volume or move to Postgres.

## Ubuntu 24/7 Hosting

1. Install Docker and the Compose plugin.
2. Clone or copy this project onto the server.
3. Create `.env`.
4. Run `docker compose up -d --build`.
5. Keep `./data` backed up.

For LAN access, visit `http://SERVER_LAN_IP:8050`. For private remote access, use Tailscale, WireGuard, or a private Cloudflare Tunnel. Do not expose the dashboard publicly unless you add authentication in front of it.

## Dashboard Pages

- `/` shows linked users, daily games, ranked games, LP movement, leaderboard, and server graphs.
- `/player/<discord_user_id>` shows player KPIs, filters, match table, LP trend, champion performance, role performance, queues, and duration charts.
- `/compare` compares two opted-in players.
- `/champion` focuses on one player and champion.

Screenshot placeholders:

- Server overview: leaderboard and daily activity charts.
- Player profile: KPIs, LP trend, match history.
- Compare players: grouped metric bars.
- Champion analytics: champion-specific stats and best/worst recent games.

## Privacy And Consent

Users are tracked only after `/optin` or `/lol_link`, and they can stop tracking with `/optout`. `/delete_my_data` removes their user row, Riot link, matches, ranked snapshots, presence sessions, and daily summaries.

The dashboard is intended to be internal/private. Use network-level access controls or a private tunnel.

## Tests

```bash
pytest
```
