import os
import sys
import asyncio
import logging
from typing import List, Optional
from datetime import date, time, datetime
from dateutil.relativedelta import relativedelta
from dataclasses import dataclass, field
from pytz import timezone
import caldav
import telegram
from telegram.constants import ParseMode

DEFAULT_LOG_LEVEL = 'INFO'
log_level = os.environ.get('LOG_LEVEL', DEFAULT_LOG_LEVEL)
logging_mapping = logging.getLevelNamesMapping()
if log_level in logging_mapping:
    logging.basicConfig(format='%(asctime)s - %(message)s', level=logging_mapping[log_level])
else:
    logging.basicConfig(format='%(asctime)s - %(message)s', level=logging_mapping[DEFAULT_LOG_LEVEL])
    logging.error(f'Invalid LogLevel: {log_level}')


class Config:
    """Configuration class for managing configuration settings."""

    def __init__(self):
        """Initialize configuration settings from environment variables or default values."""
        self.CALDAV_URL = os.environ.get('CALDAV_URL', None)
        self.CALDAV_USERNAME = os.environ.get('CALDAV_USERNAME', None)
        self.CALDAV_PASSWORD = os.environ.get('CALDAV_PASSWORD', None)
        self.CALENDAR_IDS = os.environ.get('CALENDAR_IDS', None)
        self.SYNC_INTERVAL_IN_SEC = os.environ.get('SYNC_INTERVAL_IN_SEC', 1800)
        self.FETCH_EVENT_WINDOW_IN_DAYS = os.environ.get('FETCH_EVENT_WINDOW_IN_DAYS', 5)
        self.TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', None)
        self.TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', None)
        self.TIMEZONE = timezone(os.environ.get('TIMEZONE', 'UTC'))

        self.CALENDAR_IDS = self.CALENDAR_IDS.split(";") if self.CALENDAR_IDS else None


@dataclass(order=True)
class Reminder:
    """Class representing a reminder."""
    dt: datetime
    valarm: caldav.vobject.base.Component
    vevent: caldav.vobject


@dataclass()
class Event:
    """Class representing an event."""
    vevent: caldav.vobject
    reminders: List[Reminder] = field(default_factory=list, init=False)


class CaldavHandler:
    """Handler for interacting with CalDAV server."""

    def __init__(self, config: Config):
        """Initialize CalDAV handler instance."""
        self.principal = None
        self.dav_client = None
        self.config: Config = config

    def login(self, caldav_url: str, username: str, password: str) -> bool:
        """Create CalDAV client and login to the server."""
        logging.debug(f'Creating caldav client: {caldav_url=}, {username=}')

        # Initiating the client object will not cause any server communication,
        # so the credentials aren't validated.
        self.dav_client = caldav.DAVClient(
            url=caldav_url,
            username=username,
            password=password
        )

        # This will cause communication with the server.
        logging.debug('Fetching principal object')
        try:
            self.principal = self.dav_client.principal()
            return True
        except caldav.lib.error.AuthorizationError as e:
            logging.warning(f'{e}')
            return False

    def fetch_calendars(self) -> Optional[List[caldav.objects.Calendar]]:
        """Fetch the list of calendars from the server.
        :return: A list of calendars or None if not logged in.
        """
        if self.principal is None:
            logging.error('Cannot fetch calendars: Not logged in')
            return None

        logging.debug('Fetching calendars')
        calendars = self.principal.calendars()

        if logging.getLogger().level == logging.DEBUG:
            logged_calendar = ''
            for calendar in calendars:
                logged_calendar += f'\t{calendar.name} ({calendar.id}): {calendar.url}\n'

            logging.debug(f'Fetched calendars:\n{logged_calendar}')

        return calendars

    def fetch_events(self, calendars: List[caldav.objects.Calendar]) -> List[Event]:
        """Fetch the events from the specified calendars.
        :param calendars: List of Calendar objects to fetch events from.
        :return: A list of Event objects.
        """
        logging.debug(f'Fetching events for {[cal.id for cal in calendars]}')
        eventsData: List[Event] = []
        for item in calendars:
            calendar = self.dav_client.calendar(url=item.url)
            start = datetime.now(tz=self.config.TIMEZONE)
            end = datetime.now(tz=self.config.TIMEZONE) + \
                relativedelta(days=int(self.config.FETCH_EVENT_WINDOW_IN_DAYS))
            logging.debug(f'Searching for events. Range: [{str(start)}, {str(end)}]')

            events = calendar.search(
                event=True,
                expand=True,
                start=start,
                end=end,
            )

            for event in events:
                vevent = event.vobject_instance.vevent
                dtstart = vevent.dtstart.value

                if type(dtstart) == date:
                    dtstart = datetime.combine(dtstart, time(0, 0))

                if (dtstart.tzinfo is None or dtstart.tzinfo.utcoffset(dtstart) is None):
                    dtstart = self.config.TIMEZONE.localize(dtstart)

                vevent.dtstart.value = dtstart.astimezone(self.config.TIMEZONE)
                dtstart = vevent.dtstart.value
                event = Event(vevent=vevent)

                for valarm in vevent.components():
                    alarm_dt = dtstart + valarm.trigger.value
                    event.reminders.append(Reminder(dt=alarm_dt, valarm=valarm, vevent=vevent))

                eventsData.append(event)

        if logging.getLogger().level == logging.DEBUG:
            logged_events = ''
            for event in eventsData:
                logged_events += \
                    f'\t{event.vevent.summary.value} ({event.vevent.uid.value}): {event.vevent.dtstart.value}\n'

            logging.debug(f'Fetched events:\n{logged_events}')
        return eventsData

    def extract_reminders(self, events: List[Event]) -> List[Reminder]:
        """Extract reminders from the fetched events.
        :param events: List of Event objects to extract reminders from.
        :return: A list of Reminder objects.
        """
        logging.debug(f'Extracting Reminders from events: {[event.vevent.uid.value for event in events]}')
        reminders: List[Reminder] = []
        for event in events:
            for reminder in event.reminders:
                if reminder.dt >= datetime.now(tz=self.config.TIMEZONE):
                    reminders.append(reminder)

        reminders.sort()
        if logging.getLogger().level == logging.DEBUG:
            logged_events = ''
            for reminder in reminders:
                logged_events += f'\t{reminder.vevent.summary.value}: {reminder.dt}\n'

            logging.debug(f'Extracted reminders:\n{logged_events}')
        return reminders


class Worker:
    """Worker class for managing reminders and synchronization."""

    def __init__(self, config: Config, calHandler: CaldavHandler):
        """Initialize Worker instance with CaldavHandler."""
        self.sorted_reminders: List[Reminder] = []
        self.reminder_task: asyncio.Task = None
        self.calHandler: CaldavHandler = calHandler
        self.config: Config = config
        self.next_sync_dt = datetime.now(tz=self.config.TIMEZONE)
        self.cals: List[caldav.objects.Calendar] = None
        self.event_loop = asyncio.new_event_loop()

    async def run_at(self, dt, coro):
        """Run the specified coroutine at the specified datetime."""
        try:
            now = datetime.now(tz=self.config.TIMEZONE)
            await asyncio.sleep((dt - now).total_seconds())
            return await coro()
        except asyncio.CancelledError:
            pass

    def run(self):
        """Run the main event loop for synchronization and reminder processing."""
        self.event_loop.create_task(self.sync())
        self.event_loop.run_forever()

    def scheduleReminderTask(self):
        """Schedule the next reminder task based on the sorted reminders list."""
        if self.reminder_task:
            self.reminder_task.cancel()

        if len(self.sorted_reminders) > 0:
            self.reminder_task = self.event_loop.create_task(self.run_at(self.sorted_reminders[0].dt, self.process_reminders))

    async def sync(self) -> None:
        """Synchronize calendars and reminders with the server."""
        logging.info('Syncing...')
        try:
            if self.cals is None:
                self.cals = self.calHandler.fetch_calendars()
                if self.cals is None:
                    logging.error('Cannot sync calendar')
                    return

            cals_subscripted = list(filter(lambda x: x.id in self.config.CALENDAR_IDS, self.cals))
            events = self.calHandler.fetch_events(cals_subscripted)
            if events:
                sorted_reminders_new = self.calHandler.extract_reminders(events)
                if sorted_reminders_new != self.sorted_reminders:
                    self.sorted_reminders = sorted_reminders_new
                    self.scheduleReminderTask()

            next_sync_dt = datetime.now(tz=self.config.TIMEZONE) + \
                relativedelta(seconds=int(self.config.SYNC_INTERVAL_IN_SEC))
        except Exception as e:
            logging.error(f'Exception occured: {e}')
        finally:
            loop = asyncio.get_event_loop()
            loop.create_task(self.run_at(next_sync_dt, self.sync))

    async def process_reminders(self):
        """Process reminders and send notifications."""
        self.reminder_task = None
        try:
            logging.debug('Processing reminders')
            while await self.process_next_reminder():
                pass
            self.scheduleReminderTask()
        except asyncio.CancelledError:
            logging.debug('cancel processing reminders')
            pass

    async def process_next_reminder(self):
        """Process the next reminder in the sorted reminders list."""
        if len(self.sorted_reminders) > 0:
            reminder = self.sorted_reminders.pop(0)
            if reminder.dt <= datetime.now(tz=self.config.TIMEZONE):
                logging.info(f'Sending reminder for {reminder.vevent.summary.value}')
                bot = telegram.Bot(self.config.TELEGRAM_BOT_TOKEN)
                await bot.send_message(text=f'<b>Reminder</b>\r\n{reminder.vevent.summary.value}: {reminder.vevent.dtstart.value.strftime("%d.%m.%Y %H:%M:%S")}',
                                       chat_id=self.config.TELEGRAM_CHAT_ID, parse_mode=ParseMode.HTML)
                return True
        return False


if __name__ == '__main__':
    """Main entry point for the script."""
    config = Config()

    if config.CALDAV_URL is None:
        logging.error('Cannot start. CALDAV_URL not set.')
        sys.exit(1)

    if config.CALDAV_USERNAME is None or config.CALDAV_PASSWORD is None:
        logging.error('Cannot start. CALDAV_USERNAME or CALDAV_PASSWORD not set.')
        sys.exit(1)

    if config.TELEGRAM_BOT_TOKEN is None or config.TELEGRAM_CHAT_ID is None:
        logging.error('Cannot start. TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set.')
        sys.exit(1)

    caldav_handler = CaldavHandler(config)
    result = caldav_handler.login(caldav_url=config.CALDAV_URL, username=config.CALDAV_USERNAME, password=config.CALDAV_PASSWORD)
    if result is False:
        logging.error('Cannot start: Login failed')
        sys.exit(1)
    worker = Worker(config, caldav_handler)
    worker.run()
