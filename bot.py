import json
import os
import random
import time
import mimetypes
import urllib.request
import urllib.error
import uuid
from pathlib import Path

# ZiyoDrive Telegram test bot
# Faqat loyihadagi mahalliy rasmlardan foydalanadi.
# Internetdan rasm qidirmaydi va rasm manbasi yozuvini yubormaydi.

BASE_DIR = Path(__file__).resolve().parent
QUESTIONS_FILE = BASE_DIR / "questions.json"
IMAGE_DIRS = [
    BASE_DIR / "images" / "candidates",
    BASE_DIR / "images",
    BASE_DIR / "images" / "source",
]
CHANNEL = os.getenv("CHANNEL_ID", "@ziyodrive")
BOT_TOKEN = os.getenv("BOT_TOKEN")

QUESTIONS_PER_BATCH = 20
DELAY_BETWEEN_QUESTIONS = 2


def telegram_request(method, fields=None, photo_path=None):
    """Telegram Bot API so'rovini yuboradi."""
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN GitHub Secrets ichida topilmadi.")

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    fields = fields or {}

    if photo_path:
        boundary = "----ZiyoDrive" + uuid.uuid4().hex
        body = bytearray()

        for key, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
            )
            body.extend(str(value).encode("utf-8"))
            body.extend(b"\r\n")

        photo_path = Path(photo_path)
        content_type = mimetypes.guess_type(photo_path.name)[0] or "application/octet-stream"
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            (
                f'Content-Disposition: form-data; name="photo"; '
                f'filename="{photo_path.name}"\r\n'
            ).encode()
        )
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
        body.extend(photo_path.read_bytes())
        body.extend(f"\r\n--{boundary}--\r\n".encode())

        request = urllib.request.Request(
            url,
            data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
    else:
        data = json.dumps(fields, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram API xatosi ({method}): {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Telegram bilan aloqa xatosi: {exc}") from exc

    if not result.get("ok"):
        raise RuntimeError(f"Telegram API xatosi ({method}): {result}")
    return result.get("result")


def load_questions():
    if not QUESTIONS_FILE.is_file():
        raise FileNotFoundError("questions.json fayli topilmadi.")

    with QUESTIONS_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list) or not data:
        raise ValueError("questions.json ichida savollar ro'yxati bo'lishi kerak.")

    valid = []
    for number, question in enumerate(data, start=1):
        if not isinstance(question, dict):
            print(f"{number}-savol o'tkazib yuborildi: noto'g'ri format.")
            continue

        text = question.get("question")
        options = question.get("options")
        answer = str(question.get("answer", "")).strip().upper()

        if (
            not isinstance(text, str)
            or not text.strip()
            or not isinstance(options, list)
            or len(options) != 4
            or answer not in ("A", "B", "C", "D")
            or not all(isinstance(option, str) and option.strip() for option in options)
        ):
            print(f"{number}-savol o'tkazib yuborildi: savol/variant/javobni tekshiring.")
            continue

        valid.append(question)

    if not valid:
        raise ValueError("Yuborishga yaroqli savollar topilmadi.")
    return valid


def find_local_image(filename):
    """Faqat image_file maydonida aniq berilgan mahalliy faylni topadi."""
    if not filename or not isinstance(filename, str):
        return None

    # Papkadan tashqariga chiqishga yo'l qo'ymaymiz.
    safe_name = Path(filename).name
    if safe_name != filename or safe_name in ("", ".", ".."):
        print(f"Xavfsiz bo'lmagan rasm nomi o'tkazib yuborildi: {filename}")
        return None

    for folder in IMAGE_DIRS:
        candidate = folder / safe_name
        if candidate.is_file():
            return candidate

    # Fayl nomi kengaytmasiz berilgan bo'lsa, faqat shu nomga mos
    # jpg/jpeg/png faylni qidiradi. Tasodifiy rasm tanlamaydi.
    if not Path(safe_name).suffix:
        for folder in IMAGE_DIRS:
            for extension in (".jpg", ".jpeg", ".png", ".webp"):
                candidate = folder / f"{safe_name}{extension}"
                if candidate.is_file():
                    return candidate

    print(f"Mos rasm topilmadi; savol rasmsiz yuboriladi: {safe_name}")
    return None


def send_question(question, index, total):
    image_path = find_local_image(question.get("image_file"))

    # Rasm faqat savolda aniq ko'rsatilgan image_file bo'lsa yuboriladi.
    if image_path:
        telegram_request(
            "sendPhoto",
            fields={"chat_id": CHANNEL},
            photo_path=image_path,
        )

    options = question["options"]
    answer_index = "ABCD".index(str(question["answer"]).strip().upper())
    explanation = str(question.get("explanation", "")).strip()

    poll_fields = {
        "chat_id": CHANNEL,
        "question": f"{index}/{total}. {question['question']}",
        "options": json.dumps(options, ensure_ascii=False),
        "type": "quiz",
        "correct_option_id": answer_index,
        "is_anonymous": True,
    }
    if explanation:
        poll_fields["explanation"] = explanation[:200]

    telegram_request("sendPoll", fields=poll_fields)
    print(f"{index}/{total}-savol yuborildi.")


def main():
    questions = load_questions()
    batch = random.sample(questions, min(QUESTIONS_PER_BATCH, len(questions)))

    print(f"{len(batch)} ta test yuborish boshlandi: {CHANNEL}")
    for index, question in enumerate(batch, start=1):
        try:
            send_question(question, index, len(batch))
        except Exception as error:
            print(f"{index}-savol yuborilmadi: {error}")
        if index < len(batch):
            time.sleep(DELAY_BETWEEN_QUESTIONS)

    print("Test yuborish jarayoni tugadi.")


if __name__ == "__main__":
    main()
