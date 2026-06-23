from __future__ import annotations

from itertools import combinations


THIRD_PLACE_TARGETS = {
    74: set("ABCDF"),
    77: set("CDFGH"),
    79: set("CEFHI"),
    80: set("EHIJK"),
    81: set("BEFIJ"),
    82: set("AEHIJ"),
    85: set("EFGIJ"),
    87: set("DEIJL"),
}


def validate_third_place_matrix(rows: list[tuple[str, int, str]]) -> None:
    expected_sets = {"".join(value) for value in combinations("ABCDEFGHIJKL", 8)}
    by_set: dict[str, dict[int, str]] = {}
    for group_set, match_number, source_group in rows:
        by_set.setdefault(group_set, {})[match_number] = source_group
    if set(by_set) != expected_sets:
        raise ValueError("Annex C must contain all 495 qualifying-group combinations")
    for group_set, assignments in by_set.items():
        if set(assignments) != set(THIRD_PLACE_TARGETS):
            raise ValueError(f"{group_set} does not assign all eight third-place slots")
        if set(assignments.values()) != set(group_set):
            raise ValueError(f"{group_set} does not use every qualifying group exactly once")
        for match_number, group in assignments.items():
            if group not in THIRD_PLACE_TARGETS[match_number]:
                raise ValueError(f"Group {group} is not eligible for match {match_number}")


KNOCKOUT_FEEDERS: dict[int, tuple[int, int]] = {
    89: (74, 77), 90: (73, 75), 91: (76, 78), 92: (79, 80),
    93: (83, 84), 94: (81, 82), 95: (86, 88), 96: (85, 87),
    97: (89, 90), 98: (93, 94), 99: (91, 92), 100: (95, 96),
    101: (97, 98), 102: (99, 100), 104: (101, 102),
}

ROUND_32: dict[int, tuple[tuple[str, str], tuple[str, str]]] = {
    73: (("runner", "A"), ("runner", "B")),
    74: (("winner", "E"), ("third", "74")),
    75: (("winner", "F"), ("runner", "C")),
    76: (("winner", "C"), ("runner", "F")),
    77: (("winner", "I"), ("third", "77")),
    78: (("runner", "E"), ("runner", "I")),
    79: (("winner", "A"), ("third", "79")),
    80: (("winner", "L"), ("third", "80")),
    81: (("winner", "D"), ("third", "81")),
    82: (("winner", "G"), ("third", "82")),
    83: (("runner", "K"), ("runner", "L")),
    84: (("winner", "H"), ("runner", "J")),
    85: (("winner", "B"), ("third", "85")),
    86: (("winner", "J"), ("runner", "H")),
    87: (("winner", "K"), ("third", "87")),
    88: (("runner", "D"), ("runner", "G")),
}
