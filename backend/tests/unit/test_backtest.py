from world_cup_api.modeling.backtest import walk_forward_group_backtest
from world_cup_api.services.seed import seed_database


def test_walk_forward_backtest_on_finished_group_matches(db_session) -> None:
    seed_database(db_session)
    report = walk_forward_group_backtest(db_session, tournament_id=1)
    assert report.matches >= 30
    assert 0.85 < report.metrics.log_loss < 1.2


def test_style_backtest_report_has_sane_bounds(db_session) -> None:
    from world_cup_api.modeling.backtest import walk_forward_style_backtest

    seed_database(db_session)
    report = walk_forward_style_backtest(db_session, tournament_id=1)
    assert report.matches >= 30
    assert 0.5 < report.baseline_log_loss < 1.5
    assert 0.5 < report.style_log_loss < 1.5
    assert report.xg_rmse_baseline >= 0
    assert report.xg_rmse_style >= 0
