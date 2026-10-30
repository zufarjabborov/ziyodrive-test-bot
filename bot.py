import os
import json
import random
import time
import urllib.request
import urllib.parse
import urllib.error
import mimetypes
import re
import unicodedata
from pathlib import Path

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL = "@ziyodrive"
TEST_COUNT = 20
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}/"

ROOT = Path(__file__).resolve().parent
QUESTIONS_FILE = ROOT / "questions.json"
LOCAL_IMAGES_DIR = ROOT / "images" / "candidates"

LETTERS = ["A", "B", "C", "D"]


def normalize(text):
    """Uzbek matnini fayl nomlari bilan solishtirish uchun soddalashtiradi."""
    text = str(text or "").lower()
    replacements = {
        "ў": "o", "қ": "q", "ғ": "g", "ҳ": "h",
        "ў": "o", "ʼ": "'", "‘": "'", "’": "'", "ʻ": "'",
        "ş": "s", "ı": "i"
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def telegram(method, data=None, file_path=None):
    url = TELEGRAM_API + method

    if file_path:
        boundary = "----ZiyoDriveBoundary7MA4YWxkTrZu0gW"
        fields = {"chat_id": CHANNEL}
        body = bytearray()
        for key, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
            )

        path = Path(file_path)
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            f'Content-Disposition: form-data; name="photo"; filename="{path.name}"\r\n'.encode()
        )
        body.extend(f"Content-Type: {mime}\r\n\r\n".encode())
        body.extend(path.read_bytes())
        body.extend(f"\r\n--{boundary}--\r\n".encode())
        request = urllib.request.Request(
            url,
            data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
    else:
        payload = urllib.parse.urlencode(data or {}).encode("utf-8")
        request = urllib.request.Request(url, data=payload)

    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                result = json.loads(response.read().decode("utf-8"))
            if not result.get("ok"):
                raise RuntimeError(result.get("description", "Telegram xatosi"))
            time.sleep(1.1)
            return result
        except urllib.error.HTTPError as error:
            body_text = error.read().decode("utf-8", errors="replace")
            try:
                result = json.loads(body_text)
            except json.JSONDecodeError:
                raise RuntimeError(body_text)
            if error.code == 429:
                wait = result.get("parameters", {}).get("retry_after", 10)
                print(f"Telegram kutishni so‘radi: {wait} soniya")
                time.sleep(wait + 1)
                continue
            raise RuntimeError(result.get("description", body_text))
    raise RuntimeError("Telegramga yuborish qayta urinishlardan keyin ham amalga oshmadi")


def send_message(message):
    telegram("sendMessage", {"chat_id": CHANNEL, "text": message})


def topic_for_question(question):
    """Savolning mavzusini savol maydonlari va matnidan aniqlashga urinadi."""
    fields = [
        question.get("topic", ""),
        question.get("category", ""),
        question.get("section", ""),
        question.get("question", "")
    ]
    text = normalize(" ".join(str(x) for x in fields))

    groups = [
        ("yotiq_chiziqlar", ["yotiq chiziq", "yotiq chiziqlar", "qatnov qismidagi chiziq", "yo l chizig i"]),
        ("tik_chiziqlar", ["tik chiziq", "tik chiziqlar"]),
        ("xavfli_yuk_belgilari", ["xavfli yuk", "xavfli yuk belgisi"]),
        ("yol_belgilari", ["belgi", "yo l belgisi", "ogohlantiruvchi", "taqiqlovchi", "buyuruvchi", "imtiyoz", "servis"]),
    ]
    for folder_key, keywords in groups:
        if any(normalize(k) in text for k in keywords):
            return folder_key
    return None


def local_image_for_question(question):
    """
    Faqat ZIP arxividan ajratilgan images/candidates ichidagi mahalliy
    rasmlarni ishlatadi. image_url va image_search maydonlari ataylab e'tiborsiz.
    """
    if not LOCAL_IMAGES_DIR.exists():
        return None

    topic = topic_for_question(question)
    candidates = [
        p for p in LOCAL_IMAGES_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        and not p.name.startswith("._")
    ]
    if not candidates:
        return None

    if topic:
        matching = [p for p in candidates if topic in normalize(p.name).replace(" ", "_")]
        if matching:
            return random.choice(matching)

    # Noma'lum mavzuga boshqa mavzudagi rasmni qo'shib yubormaymiz.
    return None


def send_photo_without_caption(photo_path):
    # Faqat mahalliy fayl yuboriladi; caption/manba yozuvi umuman berilmaydi.
    telegram("sendPhoto", file_path=photo_path)


def send_quiz(number, question):
    options = question["options"]
    correct_letter = str(question["answer"]).strip().upper()

    if correct_letter not in LETTERS:
        raise ValueError(f"{number}-savolning javobi A/B/C/D bo‘lishi kerak")
    if len(options) != 4:
        raise ValueError(f"{number}-savolda aynan 4 ta variant bo‘lishi kerak")

    data = {
        "chat_id": CHANNEL,
        "question": f"{number}. {question['question']}",
        "options": json.dumps(options, ensure_ascii=False),
        "type": "quiz",
        "correct_option_id": LETTERS.index(correct_letter),
        "is_anonymous": "true",
        "allows_multiple_answers": "false"
    }
    if question.get("explanation"):
        data["explanation"] = str(question["explanation"])[:200]

    telegram("sendPoll", data)


def main():
    with QUESTIONS_FILE.open("r", encoding="utf-8") as file:
        questions = json.load(file)

    if not isinstance(questions, list):
        raise ValueError("questions.json eng yuqori darajada savollar ro‘yxati bo‘lishi kerak")
    if len(questions) < TEST_COUNT:
        raise ValueError(f"Bazada kamida {TEST_COUNT} ta savol bo‘lishi kerak")

    selected = random.sample(questions, TEST_COUNT)

    local_count = sum(1 for q in selected if local_image_for_question(q))
    print(f"Tanlangan savollar: {TEST_COUNT}; mahalliy rasm mos kelganlari: {local_count}")
    print("Internetdan rasm qidirish o‘chirilgan. Rasm manbasi captioni yuborilmaydi.")

    send_message(
        "🚘 ZIYODRIVE TEST\n\n"
        "Bugungi test boshlandi!\n"
        "20 ta savolga javob bering."
    )

    for number, question in enumerate(selected, 1):
        image_path = local_image_for_question(question)
        if image_path:
            try:
                send_photo_without_caption(image_path)
            except Exception as error:
                print(f"{number}-savol uchun mahalliy rasm yuborilmadi: {error}")

        send_quiz(number, question)

    send_message(
        "🏁 ZIYODRIVE TEST YAKUNLANDI!\n\n"
        "Barcha 20 ta savol yuborildi.\n"
        "Faol qatnashganingiz uchun rahmat!"
    )
    print("Test muvaffaqiyatli yuborildi!")


if __name__ == "__main__":
    main()
