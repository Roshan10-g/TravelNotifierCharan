import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is missing in environment or .env file!")

TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
DEFAULT_BUS_ALERT_METERS = int(os.getenv("DEFAULT_ALERT_DISTANCE_BUS_METERS", "500"))
DEFAULT_METRO_ALERT_METERS = int(os.getenv("DEFAULT_ALERT_DISTANCE_METRO_METERS", "800"))
DEFAULT_ARRIVAL_RADIUS_METERS = 250
