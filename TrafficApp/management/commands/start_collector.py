from django.core.management.base import BaseCommand
import time
from traffic_collector.scheduler import TrafficScheduler
from traffic_context.logger import logger

class Command(BaseCommand):
    help = 'Starts the automated traffic collection scheduler'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting Traffic Collector Scheduler...'))
        
        scheduler = TrafficScheduler()
        try:
            scheduler.start()
            self.stdout.write(self.style.SUCCESS('Scheduler is running in background. Press Ctrl+C to stop.'))
            
            # Keep the main thread alive while the background scheduler runs
            while True:
                time.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            scheduler.stop()
            self.stdout.write(self.style.WARNING('Scheduler stopped.'))
        except Exception as e:
            logger.error(f"Command Error: {e}")
            self.stdout.write(self.style.ERROR(f'Error: {e}'))
