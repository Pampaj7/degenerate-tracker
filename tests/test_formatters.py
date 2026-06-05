from app.formatters import compute_kda, compute_winrate, format_duration, rank_label, rank_points


def test_format_duration():
    assert format_duration(None) == "0m"
    assert format_duration(42) == "42s"
    assert format_duration(125) == "2m 5s"
    assert format_duration(3720) == "1h 2m"


def test_compute_kda_handles_zero_deaths():
    assert compute_kda(7, 0, 5) == 12.0
    assert compute_kda(6, 3, 6) == 4.0


def test_compute_winrate():
    assert compute_winrate(0, 0) == 0.0
    assert compute_winrate(3, 4) == 75.0


def test_rank_helpers():
    assert rank_points("GOLD", "IV", 50) < rank_points("GOLD", "III", 0)
    assert rank_label("MASTER", None, 22) == "Master 22 LP"

