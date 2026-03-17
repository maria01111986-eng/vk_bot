from vkbottle.dispatch.rules.base import PayloadRule
print(f"PayloadRule: {PayloadRule}")
from vkbottle import Bot, Message
bot = Bot("token")
print(f"bot.on.private_message: {bot.on.private_message}")
try:
    from vkbottle.bot import Message
    print("Message imported")
except ImportError:
    print("Message import failed")
