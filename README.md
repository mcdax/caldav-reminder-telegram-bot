# CalDAV Reminder Telegram Bot

This bot synchronizes with a CalDAV server, fetches events, and sends reminders for these events to a specified Telegram chat.

## Running Without Docker

1. Ensure you have Python 3.8 or above installed.
2. Install the required libraries by running: `pip install -r requirements.txt`.
3. Set the necessary [environment variables](#environment-variables): `CALDAV_URL`, `CALDAV_USERNAME`, `CALDAV_PASSWORD`, `CALENDAR_IDS`, `SYNC_INTERVAL_IN_SEC`, `FETCH_EVENT_WINDOW_IN_DAYS`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `TIMEZONE`.
    ```bash
    export CALDAV_URL=https://<url>/SOGo/dav/
    export CALDAV_USERNAME=<username>
    export CALDAV_PASSWORD=<password>
    export CALENDAR_IDS=cal_id1;cal_id2
    export SYNC_INTERVAL_IN_SEC=1800
    export FETCH_EVENT_WINDOW_IN_DAYS=5
    export TIMEZONE=Europe/Berlin
    export TELEGRAM_BOT_TOKEN=<token>
    export TELEGRAM_CHAT_ID=<chat_id>
    ```
4. Run the `app.py` script:
    ```bash
    python src/app.py
    ```

## Running with Docker (without docker-compose)

    docker run -d \
        --name caldav-reminder-telegram-bot \
        -e CALDAV_URL=https://<url>/SOGo/dav/ \
        -e CALDAV_USERNAME=<username> \
        -e CALDAV_PASSWORD=<password> \
        -e CALENDAR_IDS=cal_id1;cal_id2 \
        -e SYNC_INTERVAL_IN_SEC=1800 \
        -e FETCH_EVENT_WINDOW_IN_DAYS=5 \
        -e TIMEZONE=Europe/Berlin \
        -e TELEGRAM_BOT_TOKEN=<token> \
        -e TELEGRAM_CHAT_ID=<chat_id> \
        mcdax/caldav-reminder-telegram-bot:latest

Set the environment variables as described [here](#environment-variables).

## Running With Docker (with docker-compose)

1. Install Docker and Docker Compose.
2. Create a `docker-compose.yml` file with the provided template (see [docker-compose.yml.sample](https://github.com/mcdax/caldav-reminder-telegram-bot/blob/main/docker-compose.yml.sample)).
3. Fill in the necessary [environment variables](#environment-variables) in the `docker-compose.yml` file.
4. Build and start the container: 
  ```bash
docker-compose up --build -d
 ```

## Environment Variables

- `CALDAV_URL`: The URL of the CalDAV server.
- `CALDAV_USERNAME`: Username for authentication on the CalDAV server.
- `CALDAV_PASSWORD`: Password for authentication on the CalDAV server.
- `CALENDAR_IDS`: Semi-colon separated list of calendar IDs to be synced.
- `SYNC_INTERVAL_IN_SEC`: Interval in seconds at which the bot syncs with the CalDAV server.
- `FETCH_EVENT_WINDOW_IN_DAYS`: Number of days in advance to fetch events from the CalDAV server.
- `TELEGRAM_BOT_TOKEN`: Token for the Telegram bot.
- `TELEGRAM_CHAT_ID`: ID of the Telegram chat where reminders will be sent.
- `TIMEZONE`: The timezone used for date and time operations.

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE) due to compliance reasons with the used libraries.

## Credits

This project utilizes the following libraries:
- [python-caldav](https://github.com/python-caldav/caldav) for CalDAV access.
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) for interacting with the Telegram API.
