from time import perf_counter

from world_cup_api.db.session import SessionLocal
from world_cup_api.simulation.engine import build_input_snapshot, run_trials_parallel


def main() -> None:
    with SessionLocal() as db:
        snapshot, digest = build_input_snapshot(db)
    started = perf_counter()
    result = run_trials_parallel(snapshot, 10_000, 2026, 4)
    elapsed = perf_counter() - started
    champions = sum(values["champion"] for values in result["teams"].values())
    print({"input_hash": digest[:12], "completed": result["completed"], "champions": champions,
           "elapsed_seconds": round(elapsed, 3)})


if __name__ == "__main__":
    main()
