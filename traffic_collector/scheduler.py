from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
from .collector import TrafficCollector
from .logger import logger

class TrafficScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.collector = TrafficCollector()
        self.current_interval = 30 # Default normal daytime
        self.job = None

    def get_adaptive_interval(self):
        """
        - Rush hours (6:30-9:00, 16:00-19:30): 5-10 minutes
        - Normal daytime: 20-30 minutes
        - Late night (22:00-5:00): 1 hour
        """
        now = datetime.now()
        hour = now.hour
        minute = now.minute
        
        # Rush hours
        if (6 <= hour < 9) or (16 <= hour < 20):
            return 10 # every 10 mins
        # Late night
        if (hour >= 22) or (hour < 6):
            return 60 # every 1 hour
        # Normal daytime
        return 30 # every 30 mins

    def start(self):
        logger.info("Starting Traffic Scheduler...")
        self.schedule_next()
        self.scheduler.start()

    def schedule_next(self):
        interval = self.get_adaptive_interval()
        self.current_interval = interval
        
        if self.job:
            self.job.remove()
            
        self.job = self.scheduler.add_job(
            self.run_and_reschedule,
            IntervalTrigger(minutes=interval),
            id='traffic_collection_job'
        )
        logger.info(f"Scheduled next collection in {interval} minutes.")
        
        # Run once immediately on start
        self.collector.collect_all_routes()

    def run_and_reschedule(self):
        self.collector.collect_all_routes()
        
        # Check if interval needs to change
        new_interval = self.get_adaptive_interval()
        if new_interval != self.current_interval:
            logger.info(f"Updating interval from {self.current_interval} to {new_interval} minutes.")
            self.schedule_next()

    def stop(self):
        self.scheduler.shutdown()
        logger.info("Traffic Scheduler stopped.")
