"""Backgrounds tasks to run"""
from application import create_app
from config import Config
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime, timedelta
from application.models import District, Meta, Stat
from application.provider import DataProvider
from application.logger import Logger


def sync_district_data():
    """Fetch latest data from IEDCR reports"""
    try:
        # For some unknown reason, Logger.createLogger(__name__),
        # where __name__ == "application.tasks" doesn't bind
        # the handler. After some debugging, I found that anything
        # prefixing "application.*" doesn't work. According to
        # Logger.create_logger(), it assumes that a handler is
        # already binded, although it's not.

        # For the other parts it doesn't cause any problem. For example,
        # when the logger is created inside DataProvider module, the name
        # "application.provider.*" doesn't cause any problem.

        # This is a weird issue. I will look into this later. For now,
        # I will name it "tasks"
        logger = Logger.create_logger("tasks")
        logger.info("Starting sync of district data")
        if Meta.is_district_syncing():
            logger.info("A district sync is already in progress")
            return

        # set updating state to true
        Meta.set_district_syncing(True)

        # download and get updated data
        provider = DataProvider()
        new_data = (
            provider.sync_district_data()
        )  # returns list of tuple as [...(districtName, Count)]

        # flag to monitor if fetched data has changed
        has_updated = False

        # check the data against database records and update as necessary
        for (district_name, new_count, last_update) in new_data:
            # last_update time is in UTC +6
            # parse the time
            last_update = parse_time(last_update, logger)

            district = District.find_by_name(district_name)

            if district:
                if district.count != new_count:
                    # count changed from last record
                    # - save previous count
                    # - update new count
                    district.prev_count = district.count
                    district.count = new_count
                    has_updated = True
                else:
                    # count did not change
                    # - make count and prev_count same only if last change was 3 days ago
                    last_update_utc = last_update - timedelta(hours=6)
                    update_delta = datetime.utcnow() - last_update_utc

                    if update_delta.days > 3:
                        # district-level update takes on average 3+ days
                        # so it's more appropriate to keep the current prev_count
                        # for 3+ days
                        district.prev_count = district.count

                district.last_update = last_update
                district.save()
            else:
                new_district = (district_name, new_count, last_update)
                new_district.save()
                has_updated = True

        # set updating state to False as update is finished
        Meta.set_district_syncing(False)

        logger.debug(f"Has updated = {has_updated}")
        if has_updated:
            # set last updated time to now
            Meta.set_last_district_sync()
            logger.info("District sync complete (fetched new data)")
            return
        logger.info("District sync complete (already up-to-date)")
    except Exception as e:
        Meta.set_district_syncing(False)
        logger.error(f"District sync failed with error: {e}")


def parse_time(time, logger):
    sep = "." if "." in time else "/"
    try:
        # for format like "30.06.20" or "30/06/20"
        time = datetime.strptime(time, f"%d{sep}%m{sep}%y")
    except Exception as e:
        # try for format like "30.06.2020"
        time = datetime.strptime(time, f"%d{sep}%m{sep}%Y")
    except Exception as e:
        # no matching found, fallback to current time
        logger.warn(f"No parsing format found for {time}")
        time = datetime.utcnow()

    return time


def sync_stats():
    """Fetch latest stats from IEDCR website"""
    try:
        logger = Logger.create_logger("tasks")
        logger.info("Starting sync of stats data")
        if Meta.is_stats_syncing():
            logger.info("A stats sync is already in progress")
            return

        Meta.set_stats_syncing(True)

        provider = DataProvider()
        data = provider.get_stats()

        stat = Stat.get()

        # iteratively update the data
        for attr, value in data.items():
            setattr(stat, attr, value)

        stat.save()
        Meta.set_stats_syncing(False)
        logger.info("Stats sync complete")
    except Exception as e:
        Meta.set_stats_syncing(False)
        logger.error(f"Stats sync failed with error: {e}")


def run_sync_district():
    with app.app_context():
        sync_district_data()


def run_sync_stats():
    with app.app_context():
        sync_stats()


if __name__ == "__main__":
    app = create_app(Config)
    sched = BlockingScheduler()

    # schedule the job to be run every hour
    # push the app context, because app context is required for background jobs
    sched.add_job(run_sync_district, "interval", minutes=30)
    sched.add_job(run_sync_stats, "interval", minutes=18)
    sched.start()
