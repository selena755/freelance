import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ZARINPAL_MERCHANT_ID = os.getenv("ZARINPAL_MERCHANT_ID")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@YourChannelUsername")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))