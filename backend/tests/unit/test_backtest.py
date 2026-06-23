from world_cup_api.modeling.backtest import walk_forward_group_backtest
from world_cup_api.services.seed import seed_database


def test_walk_forward_backtest_on_finished_group_matches(db_session) -> None:
    seed_database(db_session)
    report = walk_forward_group_backtest(db_session, tournament_id=1)
    assert report.matches >= 30
    assert 0.9 < report.metrics.log_loss < 1.2
