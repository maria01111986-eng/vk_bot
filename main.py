import os
import logging
import sys
import asyncio
import random
from dotenv import load_dotenv

from vkbottle.bot import Bot, Message
from vkbottle import Keyboard, KeyboardButtonColor, Text, GroupEventType, GroupTypes, VKAPIError, BaseMiddleware
from vkbottle import PhotoMessageUploader, BaseStateGroup
from vkbottle.dispatch.rules.base import PayloadRule

from content_loader import send_content, get_text, get_content, get_all_content, save_content

# ==========================================
# НАСТРОЙКИ
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stdout
)

load_dotenv(override=True)

VK_API_TOKEN = os.getenv("VK_API_TOKEN")
VK_GROUP_ID = os.getenv("VK_GROUP_ID")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

if not VK_API_TOKEN or not VK_GROUP_ID:
    logging.error("VK_API_TOKEN or VK_GROUP_ID is not set in .env")
    sys.exit(1)

try:
    VK_GROUP_ID = int(str(VK_GROUP_ID).strip())
    if ADMIN_CHAT_ID:
        ADMIN_CHAT_ID = int(str(ADMIN_CHAT_ID).strip())
except (ValueError, AttributeError, TypeError):
    logging.error("Failed to parse VK_GROUP_ID or ADMIN_CHAT_ID")
    if not VK_GROUP_ID: sys.exit(1)
    ADMIN_CHAT_ID = None

bot = Bot(token=VK_API_TOKEN)
photo_uploader = PhotoMessageUploader(bot.api)

# Состояния
class FeedbackState(BaseStateGroup):
    WAITING_FOR_MESSAGE = "waiting_for_message"

class AdminState(BaseStateGroup):
    WAITING_FOR_CATEGORY = "waiting_for_category"
    WAITING_FOR_TEXT = "waiting_for_text"
    WAITING_FOR_PHOTO = "waiting_for_photo"

async def safe_delete_state(peer_id: int):
    try:
        await bot.state_dispenser.delete(peer_id)
        logging.info("Deleted state for %s", peer_id)
    except KeyError:
        pass
    except Exception as e:
        logging.error("Error deleting state for %s: %s", peer_id, e)

class MessageLoggingMiddleware(BaseMiddleware[Message]):
    async def pre(self):
        logging.info("Incoming message from %s: text=%r payload=%r", 
                     self.event.from_id, self.event.text, self.event.payload)

bot.labeler.message_view.register_middleware(MessageLoggingMiddleware)

@bot.error_handler.register_error_handler(Exception)
async def error_handler(e: Exception):
    logging.exception("Global error caught: %s", e)

# ==========================================
# КЛАВИАТУРЫ
# ==========================================

# Главное меню
main_menu = (
    Keyboard(one_time=False)
    .add(Text("🏥 При поступлении", payload={"cmd": "arrival"}), color=KeyboardButtonColor.PRIMARY)
    .add(Text("🧽 Ежедневный уход", payload={"cmd": "care_main"}), color=KeyboardButtonColor.PRIMARY)
    .row()
    .add(Text("💊 Медицинские манипуляции", payload={"cmd": "med_main"}), color=KeyboardButtonColor.PRIMARY)
    .add(Text("🧘‍♀️ Позиционирование", payload={"cmd": "pos_main"}), color=KeyboardButtonColor.PRIMARY)
    .row()
    .add(Text("🚨 Наблюдение и Красные флаги", payload={"cmd": "flags_main"}), color=KeyboardButtonColor.PRIMARY)
    .add(Text("🌿 Поддержка родителю", payload={"cmd": "support_main"}), color=KeyboardButtonColor.PRIMARY)
    .row()
    .add(Text("🧸 Коммуникация с ребенком", payload={"cmd": "comm_main"}), color=KeyboardButtonColor.PRIMARY)
    .add(Text("📝 Памятки при выписке", payload={"cmd": "discharge_main"}), color=KeyboardButtonColor.PRIMARY)
    .row()
    .add(Text("🆘 SOS / Обратная связь", payload={"cmd": "sos_main"}), color=KeyboardButtonColor.NEGATIVE)
    .row()
    .add(Text("💬 Оставьте отзыв о нашем отделении", payload={"cmd": "feedback_main"}), color=KeyboardButtonColor.SECONDARY)
).get_json()

# меню "назад"
back_menu = (
    Keyboard(one_time=False)
    .add(Text("🔙 Назад"), color=KeyboardButtonColor.SECONDARY)
).get_json()

# Инлайн-меню: Поддержка родителю
support_menu = (
    Keyboard(inline=True)
    .add(Text("😮💨 Успокоиться", payload={"cmd": "sup_calm"}))
    .add(Text("🫶 Тревожно", payload={"cmd": "sup_anxious"}))
    .row()
    .add(Text("🌙 Устали", payload={"cmd": "sup_tired"}))
    .add(Text("🤝 Помощь", payload={"cmd": "sup_help"}))
    .row()
    .add(Text("🌊 Дыхание", payload={"cmd": "sup_wave"}))
    .add(Text("🧊 Холод", payload={"cmd": "sup_cold"}))
    .row()
    .add(Text("🌳 Опора", payload={"cmd": "sup_support"}))
).get_json()

# Инлайн-меню: Ежедневный уход
care_menu = (
    Keyboard(inline=True)
    .add(Text("🛁 Купание и гигиена", payload={"cmd": "care_wash"}))
    .row()
    .add(Text("🧴 Профилактика пролежней", payload={"cmd": "care_bedsore"}))
    .row()
    .add(Text("🍼 Кормление и питье", payload={"cmd": "care_food"}))
).get_json()

# Инлайн-меню: Манипуляции
med_menu = (
    Keyboard(inline=True)
    .add(Text("💨 Ингаляции", payload={"cmd": "med_ing"}))
    .row()
    .add(Text("💉 Уколы и капельницы", payload={"cmd": "med_inj"}))
    .row()
    .add(Text("🚽 Клизма / Трубка", payload={"cmd": "med_tube"}))
    .row()
    .add(Text("⚡️ Физиотерапия", payload={"cmd": "med_phys"}))
).get_json()

# Инлайн-меню: Красные флаги
flags_menu = (
    Keyboard(inline=True)
    .add(Text("🌡 Температура", payload={"cmd": "f_temp"}))
    .add(Text("🫁 Дыхание", payload={"cmd": "f_breath"}))
    .row()
    .add(Text("🔴 Кожа и пролежни", payload={"cmd": "f_skin"}))
    .add(Text("🚽 Стул и моча", payload={"cmd": "f_stool"}))
    .row()
    .add(Text("🧠 Судороги (Памятка)", payload={"cmd": "f_seiz"}))
).get_json()

# ==========================================
# АДМИН ПАНЕЛЬ
# ==========================================

admin_skip_text_kb = (
    Keyboard(one_time=True)
    .add(Text("Пропустить (оставить текущий)"))
    .row()
    .add(Text("Отмена ❌"), color=KeyboardButtonColor.NEGATIVE)
).get_json()

admin_photo_kb = (
    Keyboard(one_time=True)
    .add(Text("Без фото 🚫"))
    .add(Text("Оставить текущее 🖼"))
    .row()
    .add(Text("Отмена ❌"), color=KeyboardButtonColor.NEGATIVE)
).get_json()

KEY_LABELS = {
    "start": "🏠 Старт (Начало)",
    "arrival": "🏥 При поступлении",
    "care_main": "🧽 Уход (Главная)",
    "nav_care": "🧭 Уход: Навигация",
    "med_main": "💊 Манипуляции (Главная)",
    "nav_med": "🧭 Манипуляции: Навиг.",
    "pos_main": "🧘‍♀️ Позиционирование",
    "flags_main": "🚨 Красные флаги (Главн.)",
    "nav_flags": "🧭 Флаги: Навигация",
    "comm_main": "🧸 Коммуникация",
    "discharge_main": "📝 Выписка",
    "support_main": "🌿 Поддержка (Главная)",
    "nav_support": "🧭 Поддержка: Навиг.",
    "sos_main": "🆘 SOS / Помощь",
    "feedback_main": "📝 Отзыв (Главная)",
    "feedback_back": "🔙 Кнопка Назад",
    "feedback_empty": "⚠️ Ошибка: Пусто",
    "feedback_prefix_review": "📝 Префикс: Отзыв",
    "feedback_prefix_sos": "📬 Префикс: SOS",
    "feedback_success": "✅ Успех отправки",
    "feedback_error": "❌ Ошибка отправки",
    "care_wash": "🛁 Уход: Гигиена",
    "care_bedsore": "🧴 Уход: Пролежни",
    "nav_bedsore": "🧭 Уход: Пролежни (Нав)",
    "b_time": "🔄 Уход: Смена поз",
    "b_creams": "🧴 Уход: Средства",
    "care_food": "🍼 Уход: Кормление",
    "med_ing": "💨 Манип: Ингаляция",
    "med_inj": "💉 Манип: Уколы",
    "med_tube": "🚽 Манип: Трубка",
    "med_phys": "⚡️ Манип: Физио",
    "f_temp": "🌡 Флаги: Температура",
    "f_breath": "🫁 Флаги: Дыхание",
    "f_skin": "🔴 Флаги: Кожа",
    "f_stool": "🚽 Флаги: Стул",
    "f_seiz": "🧠 Флаги: Судороги",
    "sup_calm": "😮💨 Подд: Успокоиться",
    "sup_anxious": "🫶 Подд: Тревога",
    "sup_tired": "🌙 Подд: Усталость",
    "sup_help": "🤝 Подд: Помощь",
    "sup_wave": "🌊 Подд: Дыхание",
    "sup_cold": "🧊 Подд: Холод",
    "sup_support": "🌳 Подд: Опора",
    "fallback": "❓ Неизвестное сообщ."
}

ADMIN_CATEGORIES = {
    "🏠 Главное": ["start", "arrival", "pos_main", "discharge_main", "sos_main", "feedback_main", "fallback"],
    "🧽 Уход": ["care_main", "nav_care", "care_wash", "care_bedsore", "nav_bedsore", "b_time", "b_creams", "care_food"],
    "💊 Манипуляции": ["med_main", "nav_med", "med_ing", "med_inj", "med_tube", "med_phys"],
    "🚨 Флаги": ["flags_main", "nav_flags", "f_temp", "f_breath", "f_skin", "f_stool", "f_seiz"],
    "🌿 Поддержка": ["support_main", "nav_support", "sup_calm", "sup_anxious", "sup_tired", "sup_help", "sup_wave", "sup_cold", "sup_support"],
    "💬 Служебное": ["feedback_back", "feedback_empty", "feedback_prefix_review", "feedback_prefix_sos", "feedback_success", "feedback_error"]
}

def is_admin(user_id: int) -> bool:
    return ADMIN_CHAT_ID is not None and user_id == ADMIN_CHAT_ID

@bot.on.private_message(text=["/admin", "админ", "Admin"])
async def cmd_admin(message: Message):
    if not is_admin(message.from_id):
        return
        
    kb = Keyboard(inline=True)
    for i, cat in enumerate(ADMIN_CATEGORIES.keys()):
        kb.add(Text(cat, payload={"adm_cat": cat}))
        if (i + 1) % 2 == 0:
            kb.row()
    
    await message.answer(
        "🛠 <b>Панель администратора</b>\nВыберите категорию для редактирования:",
        keyboard=kb.get_json()
    )

@bot.on.private_message(payload_map={"adm_cat": str})
async def admin_cat_selected(message: Message):
    if not is_admin(message.from_id):
        return
    import json
    payload = json.loads(message.payload)
    cat = payload["adm_cat"]
    keys = ADMIN_CATEGORIES.get(cat, [])
    
    kb = Keyboard(inline=True)
    for i, key in enumerate(keys):
        label = KEY_LABELS.get(key, key)
        kb.add(Text(label, payload={"adm_edit": key}))
        if (i + 1) % 2 == 0:
            kb.row()
    
    # Кнопка возврата к категориям
    kb.row().add(Text("🔙 К категориям", payload={"adm_back": "cats"}))
    
    await message.answer(
        f"📂 Категория: <b>{cat}</b>\nВыберите раздел:",
        keyboard=kb.get_json()
    )

@bot.on.private_message(payload_map={"adm_back": "cats"})
async def admin_back_to_cats(message: Message):
    await cmd_admin(message)

@bot.on.private_message(text="Отмена ❌", state=[AdminState.WAITING_FOR_TEXT, AdminState.WAITING_FOR_PHOTO])
async def admin_cancel(message: Message):
    if is_admin(message.from_id):
        await safe_delete_state(message.from_id)
        await message.answer("Редактирование отменено.", keyboard=main_menu)

@bot.on.private_message(payload_map={"adm_edit": str}) 
async def admin_edit_start(message: Message):
    if not is_admin(message.from_id):
        return
        
    import json
    payload = json.loads(message.payload)
    key = payload["adm_edit"]
    
    content = get_content(key)
    current_text = content.get("text", "")
    current_image = content.get("image")
    
    await bot.state_dispenser.set(message.from_id, AdminState.WAITING_FOR_TEXT, edit_key=key, current_text=current_text, current_image=current_image)
    
    await message.answer(
        f"Редактирование раздела: <b>{key}</b>\n\n"
        f"Текущий текст:\n{current_text}\n\n"
        "Отправьте новый ТЕКСТ или нажмите «Пропустить».",
        keyboard=admin_skip_text_kb
    )

@bot.on.private_message(state=AdminState.WAITING_FOR_TEXT)
async def admin_text_received(message: Message):
    if not is_admin(message.from_id):
        return
        
    state_payload = message.state_peer.payload
    
    if message.text == "Пропустить (оставить текущий)":
        new_text = state_payload["current_text"]
    elif message.text == "Отмена ❌":
        return
    else:
        new_text = message.text
        
    await bot.state_dispenser.set(message.from_id, AdminState.WAITING_FOR_PHOTO, **state_payload, new_text=new_text)
    
    await message.answer(
        "Текст принят. \nТеперь отправьте ФОТО или выберите действие на клавиатуре.",
        keyboard=admin_photo_kb
    )

@bot.on.private_message(state=AdminState.WAITING_FOR_PHOTO)
async def admin_photo_received(message: Message):
    if not is_admin(message.from_id):
        return
        
    state_payload = message.state_peer.payload
    key = state_payload["edit_key"]
    new_text = state_payload["new_text"]
    current_image = state_payload["current_image"]
    
    new_image = None
    if message.attachments:
        for attach in message.attachments:
            if attach.photo:
                new_image = f"photo{attach.photo.owner_id}_{attach.photo.id}"
                break
    
    if not new_image:
        if message.text == "Без фото 🚫":
            new_image = None
        elif message.text == "Оставить текущее 🖼":
            new_image = current_image
        else:
            await message.answer("Пожалуйста, прикрепите фото или воспользуйтесь кнопками ниже.", keyboard=admin_photo_kb)
            return

    # Перезаписываем данные
    content_data = get_all_content()
    content_data[key] = {
        "text": new_text,
        "image": new_image
    }
    
    save_content(content_data)
    
    await message.answer(f"✅ Данные раздела {key} успешно сохранены!", keyboard=main_menu)
    await message.answer("Вот как это выглядит теперь:")
    await send_content(message, key, bot=bot)
    
    await safe_delete_state(message.from_id)

# ==========================================
# ОБРАБОТЧИКИ: ГЛАВНОЕ МЕНЮ
# ==========================================

# ПОДРАЗДЕЛЫ (оставим для текстового ввода, но payload приоритетнее)
@bot.on.private_message(text=["тест", "Тест", "ping", "пинг"])
async def test_handler(message: Message):
    logging.info("TEST handler triggered")
    await message.answer(f"Бот работает! Пинг-понг. Ваше сообщение: {message.text}")

async def handle_command(message: Message, cmd: str):
    logging.info("HANDLE_CMD: cmd=%s from=%s", cmd, message.from_id)
    await safe_delete_state(message.from_id)
    
    if cmd == "start":
        await send_content(message, "start", reply_markup=main_menu, bot=bot)
    elif cmd == "arrival":
        await send_content(message, "arrival", reply_markup=back_menu, bot=bot)
    elif cmd == "care_main":
        await send_content(message, "care_main", reply_markup=care_menu, bot=bot)
        await send_content(message, "nav_care", reply_markup=back_menu, bot=bot)
    elif cmd == "med_main":
        await send_content(message, "med_main", reply_markup=med_menu, bot=bot)
        await send_content(message, "nav_med", reply_markup=back_menu, bot=bot)
    elif cmd == "pos_main":
        await send_content(message, "pos_main", reply_markup=back_menu, bot=bot)
    elif cmd == "flags_main":
        await send_content(message, "flags_main", reply_markup=flags_menu, bot=bot)
        await send_content(message, "nav_flags", reply_markup=back_menu, bot=bot)
    elif cmd == "comm_main":
        await send_content(message, "comm_main", reply_markup=back_menu, bot=bot)
    elif cmd == "discharge_main":
        await send_content(message, "discharge_main", reply_markup=back_menu, bot=bot)
    elif cmd == "support_main":
        await send_content(message, "support_main", reply_markup=support_menu, bot=bot)
        await send_content(message, "nav_support", reply_markup=back_menu, bot=bot)
    elif cmd == "sos_main":
        await send_content(message, "sos_main", reply_markup=back_menu, bot=bot)
        await bot.state_dispenser.set(message.from_id, FeedbackState.WAITING_FOR_MESSAGE, kind="sos")
    elif cmd == "feedback_main":
        await send_content(message, "feedback_main", reply_markup=back_menu, bot=bot)
        await bot.state_dispenser.set(message.from_id, FeedbackState.WAITING_FOR_MESSAGE, kind="review")
    elif cmd == "care_bedsore":
        kb = (
            Keyboard(inline=True)
            .add(Text("⏱ Как часто менять положение?", payload={"cmd": "b_time"}))
            .row()
            .add(Text("🧴 Какие средства использовать?", payload={"cmd": "b_creams"}))
        ).get_json()
        await send_content(message, "care_bedsore", reply_markup=kb, bot=bot)
        await send_content(message, "nav_bedsore", reply_markup=back_menu, bot=bot)
    elif cmd == "care_wash":
        await send_content(message, "care_wash", reply_markup=back_menu, bot=bot)
    elif cmd == "care_food":
        await send_content(message, "care_food", reply_markup=back_menu, bot=bot)
    elif cmd == "med_ing":
        await send_content(message, "med_ing", reply_markup=back_menu, bot=bot)
    elif cmd == "med_inj":
        await send_content(message, "med_inj", reply_markup=back_menu, bot=bot)
    elif cmd == "med_tube":
        await send_content(message, "med_tube", reply_markup=back_menu, bot=bot)
    elif cmd == "med_phys":
        await send_content(message, "med_phys", reply_markup=back_menu, bot=bot)
    elif cmd == "f_temp":
        await send_content(message, "f_temp", reply_markup=back_menu, bot=bot)
    elif cmd == "f_breath":
        await send_content(message, "f_breath", reply_markup=back_menu, bot=bot)
    elif cmd == "f_skin":
        await send_content(message, "f_skin", reply_markup=back_menu, bot=bot)
    elif cmd == "f_stool":
        await send_content(message, "f_stool", reply_markup=back_menu, bot=bot)
    elif cmd == "f_seiz":
        await send_content(message, "f_seiz", reply_markup=back_menu, bot=bot)
    elif cmd.startswith("sup_"):
        await send_content(message, cmd, reply_markup=back_menu, bot=bot)
    else:
        # Пытаемся отправить контент по ключу (для всех остальных команд)
        await send_content(message, cmd, reply_markup=back_menu, bot=bot)
# 1. ОБРАБОТЧИК PAYLOAD (Кнопки) - Самый высокий приоритет
@bot.on.private_message(PayloadRule({"cmd": str}))
async def payload_handler(message: Message):
    try:
        payload = message.get_payload_json()
        cmd = payload.get("cmd")
        logging.info("PAYLOAD MATCH: cmd=%s", cmd)
        if cmd:
            await handle_command(message, cmd)
    except Exception as e:
        logging.error("Payload error: %s", e)

# 2. КОМАНДА СТАРТ
@bot.on.private_message(text=["/start", "старт", "начать", "start", "Начать", "Старт"])
async def cmd_start(message: Message):
    logging.info("TEXT START MATCH")
    await handle_command(message, "start")

# 3. ОТЛАДКА
@bot.on.private_message(text=["/debug_content", "дебаг"])
async def debug_content_handler(message: Message):
    from content_loader import get_all_content
    data = get_all_content()
    keys = list(data.keys())
    await message.answer(f"Загружено разделов: {len(data)}. Ключи: {', '.join(keys[:10])}")

# АЛИАСЫ ДЛЯ ТЕКСТОВЫХ КНОПОК (для совместимости со старыми клавиатурами)
@bot.on.private_message(text="🏥 При поступлении")
async def alias_arrival(message: Message): await handle_command(message, "arrival")

@bot.on.private_message(text="🧽 Ежедневный уход")
async def alias_care(message: Message): await handle_command(message, "care_main")

@bot.on.private_message(text="💊 Медицинские манипуляции")
async def alias_med(message: Message): await handle_command(message, "med_main")

@bot.on.private_message(text="🧘‍♀️ Позиционирование")
async def alias_pos(message: Message): await handle_command(message, "pos_main")

@bot.on.private_message(text="🚨 Наблюдение и Красные флаги")
async def alias_flags(message: Message): await handle_command(message, "flags_main")

@bot.on.private_message(text="🌿 Поддержка родителю")
async def alias_support(message: Message): await handle_command(message, "support_main")

@bot.on.private_message(text="🧸 Коммуникация с ребенком")
async def alias_comm(message: Message): await handle_command(message, "comm_main")

@bot.on.private_message(text="📝 Памятки при выписке")
async def alias_discharge(message: Message): await handle_command(message, "discharge_main")

# ПОДРАЗДЕЛЫ (текстовые алиасы)
@bot.on.private_message(text="🚿 Купание и гигиена")
async def alias_care_wash(message: Message): await handle_command(message, "care_wash")
@bot.on.private_message(text="🛁 Купание и гигиена")
async def alias_care_wash2(message: Message): await handle_command(message, "care_wash")

@bot.on.private_message(text="🧴 Профилактика пролежней")
async def alias_care_bedsore(message: Message): await handle_command(message, "care_bedsore")

@bot.on.private_message(text="🍼 Кормление и питье")
async def alias_care_food(message: Message): await handle_command(message, "care_food")

@bot.on.private_message(text="💨 Ингаляции")
async def alias_med_ing(message: Message): await handle_command(message, "med_ing")

@bot.on.private_message(text="💉 Уколы и капельницы")
async def alias_med_inj(message: Message): await handle_command(message, "med_inj")

@bot.on.private_message(text="🚽 Клизма / Трубка")
async def alias_med_tube(message: Message): await handle_command(message, "med_tube")

@bot.on.private_message(text="⚡️ Физиотерапия")
async def alias_med_phys(message: Message): await handle_command(message, "med_phys")

@bot.on.private_message(text="🌡 Температура")
async def alias_f_temp(message: Message): await handle_command(message, "f_temp")

@bot.on.private_message(text="🫁 Дыхание")
async def alias_f_breath(message: Message): await handle_command(message, "f_breath")

@bot.on.private_message(text="🔴 Кожа и пролежни")
async def alias_f_skin(message: Message): await handle_command(message, "f_skin")

@bot.on.private_message(text="🚽 Стул и моча")
async def alias_f_stool(message: Message): await handle_command(message, "f_stool")

@bot.on.private_message(text="🧠 Судороги (Памятка)")
async def alias_f_seiz(message: Message): await handle_command(message, "f_seiz")

# СОС И ОТЗЫВЫ (текстовые алиасы)
@bot.on.private_message(text="🆘 SOS / Обратная связь")
async def alias_sos(message: Message): await handle_command(message, "sos_main")

@bot.on.private_message(text="💬 Оставьте отзыв о нашем отделении")
async def alias_feedback(message: Message): await handle_command(message, "feedback_main")

# БЛОК: ПРОФИЛАКТИКА ПРОЛЕЖНЕЙ
@bot.on.private_message(text=["⏱ Как часто менять положение?", "Как часто менять положение?"])
async def alias_b_time(message: Message): await handle_command(message, "b_time")

@bot.on.private_message(text=["🧴 Какие средства использовать?", "Какие средства использовать?"])
async def alias_b_creams(message: Message): await handle_command(message, "b_creams")

# ТЕХНИКИ ПОДДЕРЖКИ РОДИТЕЛЮ (текстовые алиасы)
@bot.on.private_message(text="😮💨 Успокоиться")
async def alias_sup_calm(message: Message): await handle_command(message, "sup_calm")

@bot.on.private_message(text="🫶 Тревожно")
async def alias_sup_anxious(message: Message): await handle_command(message, "sup_anxious")

@bot.on.private_message(text="🌙 Устали")
async def alias_sup_tired(message: Message): await handle_command(message, "sup_tired")

@bot.on.private_message(text="🤝 Помощь")
async def alias_sup_help(message: Message): await handle_command(message, "sup_help")

@bot.on.private_message(text="🌊 Дыхание")
async def alias_sup_wave(message: Message): await handle_command(message, "sup_wave")

@bot.on.private_message(text="🧊 Холод")
async def alias_sup_cold(message: Message): await handle_command(message, "sup_cold")

@bot.on.private_message(text="🌳 Опора")
async def alias_sup_support(message: Message): await handle_command(message, "sup_support")

# Обработчики SOS и Отзыв теперь в разделе алиасов выше

@bot.on.private_message(text="🔙 Назад", state=FeedbackState.WAITING_FOR_MESSAGE)
async def feedback_back_handler(message: Message):
    await safe_delete_state(message.from_id)
    await send_content(message, "feedback_back", reply_markup=main_menu, bot=bot)

@bot.on.private_message(state=FeedbackState.WAITING_FOR_MESSAGE)
async def feedback_handler(message: Message):
    if not message.text:
        await send_content(message, "feedback_empty", bot=bot)
        return

    state_payload = message.state_peer.payload
    kind = state_payload.get("kind")
    
    logging.info("Feedback from user %s kind=%s text=%r", message.from_id, kind, message.text)

    if ADMIN_CHAT_ID is None:
        logging.error("ADMIN_CHAT_ID is not set")
        await send_content(message, "feedback_error", reply_markup=main_menu, bot=bot)
        await safe_delete_state(message.from_id)
        return

    try:
        if kind == "review":
            prefix = get_text("feedback_prefix_review")
        else:
            prefix = get_text("feedback_prefix_sos")

        await bot.api.messages.send(
            peer_id=ADMIN_CHAT_ID,
            message=f"{prefix}\n\n{message.text}",
            random_id=random.getrandbits(31)
        )
        await send_content(message, "feedback_success", reply_markup=main_menu, bot=bot)
    except Exception:
        logging.exception("Error while sending message to admin")
        await send_content(message, "feedback_error", bot=bot)

    await safe_delete_state(message.from_id)

# ОБРАБОТЧИК PAYLOAD был перенесен выше для приоритета

# Обработчик для "Назад" из подразделов (если не в состоянии)
@bot.on.private_message(text="🔙 Назад")
async def general_back_handler(message: Message):
    await send_content(message, "feedback_back", reply_markup=main_menu, bot=bot)

@bot.on.raw_event(GroupEventType.MESSAGE_ALLOW, dataclass=GroupTypes.MessageAllow)
async def message_allow_handler(event: GroupTypes.MessageAllow):
    logging.info("EVENT: message_allow from %s", event.object.user_id)
    # Создаем фиктивное сообщение для handle_command
    from vkbottle.tools.dev_tools.mini_types.bot.message import MessageMin
    msg = MessageMin(from_id=event.object.user_id, peer_id=event.object.user_id)
    await handle_command(msg, "start")

# Обработчик для неизвестных сообщений
@bot.on.private_message()
async def fallback_handler(message: Message):
    logging.info("Fallback handler triggered for text: %r", message.text)
    
    # Если пользователь прислал что-то непонятное (стикер, картинку или текст) - 
    # в первый раз лучше показать приветствие, чем ошибку
    await handle_command(message, "start")

# ==========================================
# ЗАПУСК
# ==========================================
if __name__ == "__main__":
    logging.info("START: bot=%s admin=%s", VK_API_TOKEN[:10] + "...", ADMIN_CHAT_ID)
    print("Бот Заботливая медсестра (VK) запущен...")
    bot.run_forever()