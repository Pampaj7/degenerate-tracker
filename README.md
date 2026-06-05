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
- `/discord_time`, `/discord_leaderboard`, and `/game_leaderboard` show opted-in Discord online, voice, and visible game time.
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

### Invite URL

If the bot is not in your server yet:

1. Open the Discord Developer Portal.
2. Select the DegenerateTracker application.
3. Go to `OAuth2` -> `URL Generator`.
4. Select scopes:
   - `bot`
   - `applications.commands`
5. Select bot permissions:
   - `View Channels`
   - `Send Messages`
   - `Use Slash Commands`
   - `Embed Links`
   - `Read Message History`
6. Open the generated URL and invite the bot to your server.

After the bot is invited and the app is running, slash commands should appear in Discord. If global slash commands are slow to appear, set `GUILD_ID` in `.env` to your server ID and restart the app.

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

## Complete Discord Usage Guide

This is the normal flow once the bot has been invited to the server.

### 1. Start The App

Run one of these:

```bash
python -m app.main
```

or:

```bash
docker compose up -d --build
docker compose logs -f
```

Successful startup should show:

- the SQLite database was initialized
- Dash is running on port `8050`
- slash commands were synced
- the bot logged in as `DegenerateTracker`
- the Riot poller started

The dashboard is available locally at:

```text
http://127.0.0.1:8050
```

On another device in the same LAN, use the host machine IP:

```text
http://SERVER_LAN_IP:8050
```

### 2. Users Opt In

Each friend must explicitly opt in before being tracked:

```text
/optin
```

This creates the user row and allows the bot to track linked Riot data, League presence sessions, Discord online presence, and Discord voice channel time.

To stop future tracking:

```text
/optout
```

To delete all stored data:

```text
/delete_my_data
```

### 3. Users Link Riot Accounts

Each opted-in user links their Riot ID:

```text
/lol_link game_name tag_line
```

Example:

```text
/lol_link game_name:Faker tag_line:KR1
```

Do not include the `#` in the tag line. `Faker#KR1` becomes `game_name:Faker` and `tag_line:KR1`.

To unlink:

```text
/lol_unlink
```

### 4. Wait For Polling

The poller runs every `POLL_INTERVAL_SECONDS`, default `300` seconds. On each poll it:

- checks every opted-in linked account
- fetches recent match IDs
- stores new match details
- stores ranked snapshots
- recomputes daily summaries

If someone just linked their account, wait up to five minutes or restart the app to force the first poll sooner.

### 5. Daily Server Chaos

Use these commands in Discord:

```text
/status
```

Shows whether the bot is alive, how many linked users it sees, the poll interval, and the dashboard URL.

```text
/leaderboard period:today metric:games
```

Shows who has played the most today. This is the main "most degenerate" board.

Useful leaderboard variants:

```text
/leaderboard period:today metric:lp_delta
/leaderboard period:7 days metric:games
/leaderboard period:7 days metric:winrate
```

```text
/roast
/roast user:@friend
```

Generates a light roast from recent stats. It is intentionally silly, not meant to be hostile.

### 6. Discord Server Time

DegenerateTracker can also show how long opted-in users are around Discord.

Important limitation: Discord does not expose "time spent reading this specific server". The bot tracks two practical signals instead:

- online presence for opted-in server members
- time spent in voice channels in this server
- games Discord exposes as `Playing X`

User summary:

```text
/discord_time
/discord_time user:@friend period:today
```

The response includes online time, voice time, total visible game time, League-specific visible time, and the user's top visible games for that period.

Server leaderboard:

```text
/discord_leaderboard period:today metric:voice_seconds
/discord_leaderboard period:7 days metric:online_seconds
/discord_leaderboard period:week metric:game_seconds
```

Game leaderboard:

```text
/game_leaderboard period:today
/game_leaderboard period:week
```

The useful metrics are:

- `voice_seconds`
- `online_seconds`
- `game_seconds`
- `league_presence_seconds`

### 7. Player Commands

```text
/lol_today
/lol_today user:@friend
```

Shows today's games, win/loss, winrate, KDA, deaths, LP delta, and time played.

```text
/lol_week
/lol_week user:@friend
```

Same idea, but for the last seven days.

```text
/lol_recent count:5
/lol_recent user:@friend count:10
```

Shows recent stored matches with champion, queue, result, and KDA.

```text
/lol_rank
/lol_rank user:@friend
```

Shows the latest stored ranked snapshot.

```text
/lol_dashboard
/lol_dashboard user:@friend
```

Returns a direct dashboard link for that player.

```text
/lol_compare user_a:@friend1 user_b:@friend2 period:7 days
```

Compares games, winrate, LP delta, KDA, deaths, and time played.

### 8. Dashboard Workflow

Use the dashboard when the Discord commands are not enough.

Pages:

- `/` for server overview, total games, ranked games, LP movement, winners, losers, and leaderboard.
- `/player/<discord_user_id>` for detailed player stats.
- `/compare` for side-by-side player comparison.
- `/champion` for champion-specific stats.

Recommended ritual:

1. Run `/leaderboard period:today metric:games`.
2. Open `/lol_dashboard` for the current top degenerate.
3. Check playtime, deaths per game, LP delta, and champion winrate.
4. Post `/roast user:@friend` when the evidence is overwhelming.

### 9. Common Problems

Slash commands do not appear:

- restart the app
- set `GUILD_ID` in `.env` to your Discord server ID
- wait a minute after startup
- make sure the bot was invited with `applications.commands`

Presence tracking does not work:

- enable `Presence Intent` in the Discord Developer Portal
- make sure users have opted in
- make sure Discord actually shows League of Legends as their activity
- remember that text-channel reading time is not available from the Discord API

Riot linking fails:

- check `RIOT_API_KEY`
- Riot development keys expire often
- check `RIOT_REGION_CLUSTER` and `RIOT_PLATFORM_ROUTING`
- do not include `#` in the Riot tag line

Dashboard opens only on the host machine:

- use `http://SERVER_LAN_IP:8050` from other LAN devices
- set `PUBLIC_DASHBOARD_URL` if you expose it through Tailscale, WireGuard, or Cloudflare Tunnel

The leaderboard is empty:

- users need to run `/optin`
- users need to run `/lol_link`
- wait for the poller
- make sure Riot API calls are succeeding

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
