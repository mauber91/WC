import csv
from pathlib import Path

from world_cup_api.domain.bracket import validate_third_place_matrix


def test_official_annex_c_has_all_495_options() -> None:
    path = Path(__file__).resolve().parents[3] / "data" / "seed" / "annex_c.csv"
    with path.open() as handle:
        raw = list(csv.DictReader(handle))
    rows = [(row["qualified_group_set"], int(row["target_match_number"]), row["third_place_group_code"]) for row in raw]
    assert len(rows) == 495 * 8
    validate_third_place_matrix(rows)
