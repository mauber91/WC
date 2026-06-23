from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler

from world_cup_api.services.simulations import execute_simulation


scheduler = BackgroundScheduler(executors={"default": ThreadPoolExecutor(max_workers=1)}, timezone="UTC")


def shutdown_scheduler() -> None:
    if not scheduler.running:
        return
    scheduler.shutdown(wait=False)


def schedule_simulation(simulation_id: str) -> None:
    if not scheduler.running:
        scheduler.start()
    scheduler.add_job(execute_simulation, args=[simulation_id], id=f"simulation-{simulation_id}", replace_existing=True)
