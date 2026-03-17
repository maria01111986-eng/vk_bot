import json
import logging
import os
import re
import random

CONTENT_FILE = os.path.join(os.path.dirname(__file__), 'content.json')

_content_data = {}

def load_content():
    """Загружает содержимое из content.json"""
    global _content_data
    try:
        with open(CONTENT_FILE, 'r', encoding='utf-8') as f:
            _content_data = json.load(f)
    except FileNotFoundError:
        logging.error(f"Файл {CONTENT_FILE} не найден.")
        _content_data = {}
    except json.JSONDecodeError as e:
        logging.error(f"Ошибка парсинга {CONTENT_FILE}: {e}")
        _content_data = {}

def get_content(key: str) -> dict:
    """Возвращает словарь с контентом по ключу (text, image)"""
    if not _content_data:
        load_content()
    return _content_data.get(key, {"text": f"Раздел пока не заполнен. (Ключ: {key})", "image": None})

def get_text(key: str) -> str:
    """Возвращает только текст по ключу"""
    return get_content(key).get("text", f"Раздел пока не заполнен. (Ключ: {key})")

def get_all_content() -> dict:
    """Возвращает весь словарь контента. Вызывает загрузку, если пусто."""
    if not _content_data:
        load_content()
    return _content_data

def save_content(new_data: dict):
    """Сохраняет переданный словарь обратно в content.json с отступами и utf-8"""
    global _content_data
    _content_data = new_data
    try:
        with open(CONTENT_FILE, 'w', encoding='utf-8') as f:
            json.dump(_content_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Ошибка сохранения {CONTENT_FILE}: {e}")

async def send_content(target, key: str, reply_markup=None, bot=None, **kwargs):
    """
    Универсальная функция отправки контента (текст или картинка+подпись).
    target: может быть Message (vkbottle) или peer_id
    """
    content = get_content(key)
    text = content.get("text", f"Раздел пока не заполнен. (Ключ: {key})")
    
    # VK не поддерживает HTML-теги, поэтому очищаем текст
    # Также заменим <br> и подобные на перенос строки
    text = re.sub(r'<(br|BR)\s*/?>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    
    if not text.strip():
        text = f"Раздел {key} (текст отсутствует или содержит только теги)"
    
    image = content.get("image")
    
    # peer_id для отправки
    if hasattr(target, "peer_id"):
        peer_id = target.peer_id
    elif hasattr(target, "from_id"):
        peer_id = target.from_id
    else:
        peer_id = target

    logging.info("Sending content: key=%s peer_id=%s text_len=%d text_sample=%r has_image=%s", 
                 key, peer_id, len(text), text[:30] + "...", bool(image))

    random_id = random.getrandbits(31)

    if image and str(image).startswith("photo"):
        return await bot.api.messages.send(
            peer_id=peer_id,
            message=text,
            attachment=image,
            keyboard=reply_markup,
            random_id=random_id
        )
    else:
        # Если картинка есть, но она не для VK (заглушка или старый file_id), 
        # просто уведомляем в логах, но отправляем только текст.
        if image:
            logging.warning("Section %s has incompatible image format: %s", key, image)
            
        return await bot.api.messages.send(
            peer_id=peer_id,
            message=text,
            keyboard=reply_markup,
            random_id=random_id
        )
