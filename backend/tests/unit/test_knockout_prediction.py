from sqlalchemy import select

from world_cup_api.db.models import Team
from world_cup_api.services.predictions import forecast_knockout_matchup
from world_cup_api.services.seed import seed_database


def test_knockout_matchup_prediction_returns_advance_probability(db_session) -> None:
    seed_database(db_session)
    teams = db_session.scalars(select(Team).where(Team.fifa_code.in_(("MEX", "KOR")))).all()
    by_code = {team.fifa_code: team.id for team in teams}
    result = forecast_knockout_matchup(
        db_session,
        official_match_number=73,
        team_a_id=by_code["MEX"],
        team_b_id=by_code["KOR"],
    )
    assert result.official_match_number == 73
    assert result.advance_probability_a is not None
    assert 0.0 < result.advance_probability_a < 1.0
    assert result.forecast.lambda_a > 0
    assert result.forecast.lambda_b > 0
