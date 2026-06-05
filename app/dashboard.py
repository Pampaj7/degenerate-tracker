from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
from dash import Dash, Input, Output, dcc, html, dash_table

from app.analytics import aggregate_leaderboard, aggregate_user_stats, latest_rank, load_matches, player_options
from app.config import Settings
from app.formatters import format_duration

logger = logging.getLogger(__name__)


PERIOD_OPTIONS = [
    {"label": "Today", "value": "today"},
    {"label": "7 days", "value": "7 days"},
    {"label": "30 days", "value": "30 days"},
    {"label": "All", "value": "all"},
]


QUEUE_OPTIONS = [
    {"label": "All", "value": "all"},
    {"label": "Ranked Solo", "value": "ranked solo"},
    {"label": "Ranked Flex", "value": "ranked flex"},
    {"label": "ARAM", "value": "aram"},
    {"label": "Normal", "value": "normal"},
]


def _empty_figure(title: str):
    fig = px.scatter(title=title)
    fig.update_layout(template="plotly_white", annotations=[{"text": "No data yet", "showarrow": False}])
    return fig


def _card(label: str, value: Any) -> html.Div:
    return html.Div([html.Div(label, className="card-label"), html.Div(str(value), className="card-value")], className="kpi-card")


def create_dashboard(settings: Settings) -> Dash:
    db_path = settings.database_path
    app = Dash(__name__, title="DegenerateTracker Analytics", suppress_callback_exceptions=True)
    app.layout = html.Div(
        [
            dcc.Location(id="url"),
            html.Header(
                [
                    html.H1("DegenerateTracker Analytics"),
                    dcc.Link("Overview", href="/"),
                    dcc.Link("Compare", href="/compare"),
                    dcc.Link("Champion", href="/champion"),
                ],
                className="topbar",
            ),
            html.Main(id="page", className="page"),
        ]
    )

    app.index_string = """
    <!DOCTYPE html>
    <html>
      <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
          body { margin: 0; font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f6f7f9; color: #15181d; }
          .topbar { display: flex; align-items: center; gap: 18px; padding: 14px 22px; background: #111827; color: white; }
          .topbar h1 { font-size: 18px; margin: 0; margin-right: auto; }
          .topbar a { color: white; text-decoration: none; font-size: 14px; }
          .page { padding: 20px; max-width: 1400px; margin: 0 auto; }
          .grid { display: grid; gap: 14px; }
          .kpis { grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); margin-bottom: 18px; }
          .charts { grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); align-items: stretch; }
          .panel, .kpi-card { background: white; border: 1px solid #dfe3ea; border-radius: 8px; padding: 14px; }
          .card-label { color: #5f6876; font-size: 13px; }
          .card-value { font-size: 24px; font-weight: 700; margin-top: 6px; }
          .controls { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin-bottom: 16px; }
          .section-title { font-size: 20px; margin: 8px 0 14px; }
          @media (max-width: 640px) { .charts { grid-template-columns: 1fr; } .page { padding: 12px; } }
        </style>
      </head>
      <body>
        {%app_entry%}
        <footer>{%config%}{%scripts%}{%renderer%}</footer>
      </body>
    </html>
    """

    @app.callback(Output("page", "children"), Input("url", "pathname"))
    def render_page(pathname: str) -> html.Div:
        if pathname and pathname.startswith("/player/"):
            return _player_page(pathname.rsplit("/", 1)[-1], db_path)
        if pathname == "/compare":
            return _compare_page(db_path)
        if pathname == "/champion":
            return _champion_page(db_path)
        return _overview_page(db_path)

    _register_callbacks(app, db_path)
    return app


def _overview_page(db_path: Path) -> html.Div:
    board = aggregate_leaderboard("today", "games", db_path)
    today_matches = load_matches(period="today", db_path=db_path)
    linked = len(player_options(db_path))
    ranked_today = int(today_matches["queue_name"].isin(["Ranked Solo", "Ranked Flex"]).sum()) if not today_matches.empty else 0
    total_lp = int(board["lp_delta"].sum()) if not board.empty else 0
    winner = board.sort_values("lp_delta", ascending=False).head(1) if not board.empty else pd.DataFrame()
    loser = board.sort_values("lp_delta", ascending=True).head(1) if not board.empty else pd.DataFrame()

    return html.Div(
        [
            html.H2("Server Overview", className="section-title"),
            html.Div(
                [
                    _card("Linked users", linked),
                    _card("Games today", len(today_matches)),
                    _card("Ranked today", ranked_today),
                    _card("LP delta today", f"{total_lp:+d}"),
                    _card("Biggest winner", winner.iloc[0]["display_name"] if not winner.empty else "None"),
                    _card("Biggest loser", loser.iloc[0]["display_name"] if not loser.empty else "None"),
                ],
                className="grid kpis",
            ),
            html.Div(
                dash_table.DataTable(
                    data=board.to_dict("records"),
                    columns=[{"name": col.replace("_", " ").title(), "id": col} for col in board.columns],
                    sort_action="native",
                    filter_action="native",
                    page_size=10,
                ),
                className="panel",
            ),
            html.Div(
                [
                    dcc.Graph(figure=_games_per_day(today_matches)),
                    dcc.Graph(figure=_lp_delta_by_day(db_path)),
                    dcc.Graph(figure=_winrate_by_player(board)),
                    dcc.Graph(figure=_playtime_by_player(board)),
                ],
                className="grid charts",
            ),
        ]
    )


def _player_page(user_id: str, db_path: Path) -> html.Div:
    players = player_options(db_path)
    current = next((p for p in players if p["value"] == user_id), {"label": user_id})
    return html.Div(
        [
            html.H2(current["label"], className="section-title"),
            html.Div(
                [
                    dcc.Dropdown(PERIOD_OPTIONS, "7 days", id="player-period", clearable=False),
                    dcc.Dropdown(QUEUE_OPTIONS, "all", id="player-queue", clearable=False),
                    dcc.Dropdown(id="player-champion", placeholder="Champion"),
                    dcc.Dropdown(id="player-role", placeholder="Role"),
                ],
                className="controls",
            ),
            dcc.Store(id="player-id", data=user_id),
            html.Div(id="player-kpis", className="grid kpis"),
            html.Div(
                [
                    dcc.Graph(id="lp-over-time"),
                    dcc.Graph(id="player-games-per-day"),
                    dcc.Graph(id="win-loss-timeline"),
                    dcc.Graph(id="champion-winrate"),
                    dcc.Graph(id="kda-by-champion"),
                    dcc.Graph(id="deaths-per-game"),
                    dcc.Graph(id="role-performance"),
                    dcc.Graph(id="queue-distribution"),
                    dcc.Graph(id="duration-distribution"),
                ],
                className="grid charts",
            ),
            html.Div(id="match-table", className="panel"),
        ]
    )


def _compare_page(db_path: Path) -> html.Div:
    players = player_options(db_path)
    return html.Div(
        [
            html.H2("Compare Players", className="section-title"),
            html.Div(
                [
                    dcc.Dropdown(players, id="compare-a", placeholder="Player A"),
                    dcc.Dropdown(players, id="compare-b", placeholder="Player B"),
                    dcc.Dropdown(PERIOD_OPTIONS, "7 days", id="compare-period", clearable=False),
                ],
                className="controls",
            ),
            dcc.Graph(id="compare-chart"),
        ]
    )


def _champion_page(db_path: Path) -> html.Div:
    return html.Div(
        [
            html.H2("Champion Analytics", className="section-title"),
            html.Div(
                [
                    dcc.Dropdown(player_options(db_path), id="champ-user", placeholder="Player"),
                    dcc.Dropdown(id="champ-name", placeholder="Champion"),
                ],
                className="controls",
            ),
            html.Div(id="champ-kpis", className="grid kpis"),
            dcc.Graph(id="champ-lp"),
            html.Div(id="champ-games", className="panel"),
        ]
    )


def _register_callbacks(app: Dash, db_path: Path) -> None:
    @app.callback(
        Output("player-champion", "options"),
        Output("player-role", "options"),
        Input("player-id", "data"),
    )
    def player_filter_options(user_id: str):
        df = load_matches(user_id, "all", db_path=db_path)
        champions = sorted(c for c in df["champion_name"].dropna().unique()) if not df.empty else []
        roles = sorted(r for r in df["team_position"].dropna().unique() if r) if not df.empty else []
        return [{"label": c, "value": c} for c in champions], [{"label": r, "value": r} for r in roles]

    @app.callback(
        Output("player-kpis", "children"),
        Output("lp-over-time", "figure"),
        Output("player-games-per-day", "figure"),
        Output("win-loss-timeline", "figure"),
        Output("champion-winrate", "figure"),
        Output("kda-by-champion", "figure"),
        Output("deaths-per-game", "figure"),
        Output("role-performance", "figure"),
        Output("queue-distribution", "figure"),
        Output("duration-distribution", "figure"),
        Output("match-table", "children"),
        Input("player-id", "data"),
        Input("player-period", "value"),
        Input("player-queue", "value"),
        Input("player-champion", "value"),
        Input("player-role", "value"),
    )
    def update_player(user_id: str, period: str, queue: str, champion: str | None, role: str | None):
        filters = {"queue": queue, "champion": champion, "role": role}
        stats = aggregate_user_stats(user_id, period, filters, db_path)
        df = load_matches(user_id, period, filters, db_path)
        kpis = [
            _card("Current rank", latest_rank(user_id, db_path)),
            _card("Games", stats["games"]),
            _card("Wins/Losses", f"{stats['wins']}/{stats['losses']}"),
            _card("Winrate", f"{stats['winrate']}%"),
            _card("Avg KDA", stats["avg_kda"]),
            _card("Avg deaths", stats["avg_deaths"]),
            _card("LP delta", stats["lp_delta_text"]),
            _card("Time played", format_duration(stats["total_duration_seconds"])),
        ]
        return (
            kpis,
            _lp_over_time(user_id, db_path),
            _games_per_day(df),
            _win_loss_timeline(df),
            _champion_winrate(df),
            _kda_by_champion(df),
            _deaths_per_game(df),
            _role_performance(df),
            _queue_distribution(df),
            _duration_distribution(df),
            _matches_table(df),
        )

    @app.callback(Output("compare-chart", "figure"), Input("compare-a", "value"), Input("compare-b", "value"), Input("compare-period", "value"))
    def update_compare(user_a: str | None, user_b: str | None, period: str):
        if not user_a or not user_b:
            return _empty_figure("Choose two players")
        rows = []
        for user_id in (user_a, user_b):
            stats = aggregate_user_stats(user_id, period, db_path=db_path)
            label = next((p["label"] for p in player_options(db_path) if p["value"] == user_id), user_id)
            rows.extend(
                [
                    {"player": label, "metric": "Games", "value": stats["games"]},
                    {"player": label, "metric": "Winrate", "value": stats["winrate"]},
                    {"player": label, "metric": "LP Delta", "value": stats["lp_delta"]},
                    {"player": label, "metric": "Avg KDA", "value": stats["avg_kda"]},
                    {"player": label, "metric": "Avg Deaths", "value": stats["avg_deaths"]},
                    {"player": label, "metric": "Hours", "value": round(stats["total_duration_seconds"] / 3600, 2)},
                ]
            )
        return px.bar(pd.DataFrame(rows), x="metric", y="value", color="player", barmode="group", template="plotly_white")

    @app.callback(Output("champ-name", "options"), Input("champ-user", "value"))
    def champion_options(user_id: str | None):
        if not user_id:
            return []
        df = load_matches(user_id, "all", db_path=db_path)
        champions = sorted(c for c in df["champion_name"].dropna().unique()) if not df.empty else []
        return [{"label": c, "value": c} for c in champions]

    @app.callback(
        Output("champ-kpis", "children"),
        Output("champ-lp", "figure"),
        Output("champ-games", "children"),
        Input("champ-user", "value"),
        Input("champ-name", "value"),
    )
    def update_champion(user_id: str | None, champion: str | None):
        if not user_id or not champion:
            return [], _empty_figure("Choose a player and champion"), html.Div()
        stats = aggregate_user_stats(user_id, "all", {"champion": champion}, db_path)
        df = load_matches(user_id, "all", {"champion": champion}, db_path)
        kpis = [
            _card("Games", stats["games"]),
            _card("Winrate", f"{stats['winrate']}%"),
            _card("Avg KDA", stats["avg_kda"]),
            _card("LP trend", stats["lp_delta_text"]),
        ]
        return kpis, _lp_over_time(user_id, db_path), _matches_table(df.head(10))


def _games_per_day(df: pd.DataFrame):
    if df.empty:
        return _empty_figure("Games per day")
    data = df.copy()
    data["date"] = pd.to_datetime(data["game_end_timestamp"], unit="s", utc=True).dt.date
    daily = data.groupby("date").size().reset_index(name="games")
    return px.bar(daily, x="date", y="games", title="Games per day", template="plotly_white")


def _lp_delta_by_day(db_path: Path):
    with pd.option_context("mode.copy_on_write", True):
        board = aggregate_leaderboard("30 days", "games", db_path)
    if board.empty:
        return _empty_figure("LP delta by player")
    return px.bar(board, x="display_name", y="lp_delta", title="LP delta by player", template="plotly_white")


def _winrate_by_player(board: pd.DataFrame):
    if board.empty:
        return _empty_figure("Winrate by player")
    return px.bar(board, x="display_name", y="winrate", title="Winrate by player", template="plotly_white")


def _playtime_by_player(board: pd.DataFrame):
    if board.empty:
        return _empty_figure("Total playtime by player")
    data = board.copy()
    data["hours"] = data["total_time"].fillna(0) / 3600
    return px.bar(data, x="display_name", y="hours", title="Total playtime by player", template="plotly_white")


def _lp_over_time(user_id: str, db_path: Path):
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(
            """
            SELECT snapshot_ts, tier, rank, league_points
            FROM ranked_snapshots
            WHERE discord_user_id=?
            ORDER BY snapshot_ts
            """,
            conn,
            params=[user_id],
        )
    if df.empty:
        return _empty_figure("LP over time")
    df["time"] = pd.to_datetime(df["snapshot_ts"], unit="s", utc=True)
    return px.line(df, x="time", y="league_points", color="tier", title="LP over time", template="plotly_white")


def _win_loss_timeline(df: pd.DataFrame):
    if df.empty:
        return _empty_figure("Win/loss timeline")
    data = df.copy()
    data["time"] = pd.to_datetime(data["game_end_timestamp"], unit="s", utc=True)
    data["result"] = data["win"].map({1: "Win", 0: "Loss"})
    return px.scatter(data, x="time", y="champion_name", color="result", title="Win/loss timeline", template="plotly_white")


def _champion_winrate(df: pd.DataFrame):
    if df.empty:
        return _empty_figure("Champion winrate")
    data = df.groupby("champion_name").agg(games=("match_id", "count"), wins=("win", "sum")).reset_index()
    data = data[data["games"] >= 1]
    data["winrate"] = data["wins"] / data["games"] * 100
    return px.bar(data.sort_values("games", ascending=False).head(15), x="champion_name", y="winrate", title="Champion winrate", template="plotly_white")


def _kda_by_champion(df: pd.DataFrame):
    if df.empty:
        return _empty_figure("KDA by champion")
    data = df.groupby("champion_name").agg(kills=("kills", "sum"), deaths=("deaths", "sum"), assists=("assists", "sum")).reset_index()
    data["kda"] = (data["kills"] + data["assists"]) / data["deaths"].replace(0, 1)
    return px.bar(data.sort_values("kda", ascending=False).head(15), x="champion_name", y="kda", title="KDA by champion", template="plotly_white")


def _deaths_per_game(df: pd.DataFrame):
    if df.empty:
        return _empty_figure("Deaths per game")
    data = df.copy()
    data["time"] = pd.to_datetime(data["game_end_timestamp"], unit="s", utc=True)
    return px.line(data.sort_values("time"), x="time", y="deaths", title="Deaths per game", template="plotly_white")


def _role_performance(df: pd.DataFrame):
    if df.empty:
        return _empty_figure("Role performance")
    data = df.copy()
    data["role"] = data["team_position"].fillna(data["individual_position"])
    grouped = data.groupby("role").agg(games=("match_id", "count"), wins=("win", "sum")).reset_index()
    grouped["winrate"] = grouped["wins"] / grouped["games"] * 100
    return px.bar(grouped, x="role", y="winrate", title="Role performance", template="plotly_white")


def _queue_distribution(df: pd.DataFrame):
    if df.empty:
        return _empty_figure("Queue distribution")
    return px.pie(df, names="queue_name", title="Queue distribution")


def _duration_distribution(df: pd.DataFrame):
    if df.empty:
        return _empty_figure("Game duration distribution")
    data = df.copy()
    data["minutes"] = data["game_duration_seconds"].fillna(0) / 60
    return px.histogram(data, x="minutes", title="Game duration distribution", template="plotly_white")


def _matches_table(df: pd.DataFrame) -> dash_table.DataTable:
    if df.empty:
        return dash_table.DataTable(data=[], columns=[])
    data = df.copy()
    data["date"] = pd.to_datetime(data["game_end_timestamp"], unit="s", utc=True).dt.strftime("%Y-%m-%d %H:%M")
    data["result"] = data["win"].map({1: "Win", 0: "Loss"})
    data["kda"] = data.apply(lambda r: f"{int(r.kills or 0)}/{int(r.deaths or 0)}/{int(r.assists or 0)}", axis=1)
    columns = {
        "date": "Date",
        "queue_name": "Queue",
        "champion_name": "Champion",
        "team_position": "Role",
        "result": "Result",
        "kda": "KDA",
        "cs": "CS",
        "total_damage_dealt_to_champions": "Damage",
        "vision_score": "Vision",
        "game_duration_seconds": "Duration",
    }
    table = data[list(columns.keys())].rename(columns=columns)
    return dash_table.DataTable(
        data=table.to_dict("records"),
        columns=[{"name": name, "id": name} for name in table.columns],
        sort_action="native",
        filter_action="native",
        page_size=15,
        style_table={"overflowX": "auto"},
    )


def start_dashboard_in_thread(settings: Settings) -> threading.Thread:
    app = create_dashboard(settings)
    thread = threading.Thread(
        target=lambda: app.run(host=settings.dash_host, port=settings.dash_port, debug=False, use_reloader=False),
        name="dash-dashboard",
        daemon=True,
    )
    thread.start()
    logger.info("Dashboard listening on %s:%s", settings.dash_host, settings.dash_port)
    return thread

