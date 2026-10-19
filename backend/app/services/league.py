"""Shared ranking helpers for the weekly league."""


def league_ranking_key(league_score, total_xp, actual_load, user_id) -> tuple[float, float, float, int]:
    """Sort by League Score, weekly XP, weekly load, then stable user ID."""
    return (
        -float(league_score or 0.0),
        -float(total_xp or 0.0),
        -float(actual_load or 0.0),
        int(user_id or 0),
    )
