import os
import json
import random
import time
import urllib.request
import urllib.parse
import urllib.error
import urllib.parse as urlparse

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL = "@ziyodrive"
TEST_COUNT = 20

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}/"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

# Wikimedia Commons litsenziyalari: CC0, Public domain, CC BY va CC BY-SA oilalari.
ALLOWED_LICENSE_WORDS = (
    "public domain", "cc0", "cc by", "cc-by",
    "creative commons attribution", "cc by-sa", "cc-by-sa"
)


def get_json(url, headers=None):
    request = urllib.request.Request(
        url,
        headers=headers or {"User-Agent": "ZiyoDriveTestBot/1.0 (educational quiz bot)"}
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def telegram(method, data):
    url = TELEGRAM_API + method
    payload = urllib.parse.urlencode(data).encode("utf-8")

    for attempt in range(6):
        try:
            request = urllib.request.Request(url, data=payload)
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))

            if not result.get("ok"):
                raise RuntimeError(result.get("description", "Telegram xatosi"))

            time.sleep(1.2)
            return result

        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            try:
                result = json.loads(body)
            except json.JSONDecodeError:
                raise RuntimeError(body)

            if error.code == 429:
                wait = result.get("parameters", {}).get("retry_after", 10)
                print(f"Telegram kutishni so‘radi: {wait} soniya")
                time.sleep(wait + 1)
                continue

            raise RuntimeError(result.get("description", body))

    raise RuntimeError("Telegramga yuborish qayta urinishlardan keyin ham amalga oshmadi")


def send_message(message):
    telegram("sendMessage", {"chat_id": CHANNEL, "text": message})


def send_photo(photo_url, caption):
    telegram("sendPhoto", {
        "chat_id": CHANNEL,
        "photo": photo_url,
        "caption": caption[:1000]
    })


def search_commons_image(search_term):
    """
    Wikimedia Commons'dan mos rasm qidiradi.
    Faqat ochiq litsenziya/Public Domain ko‘rsatilgan fayllarni tanlaydi.
    Topilmasa None qaytaradi.
    """
    if not search_term:
        return None

    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrnamespace": 6,
        "gsrsearch": search_term,
        "gsrlimit": 12,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 1000
    }
    url = COMMONS_API + "?" + urllib.parse.urlencode(params)

    try:
        result = get_json(url)
        pages = result.get("query", {}).get("pages", {})
        candidates = list(pages.values())
        random.shuffle(candidates)

        for page in candidates:
            imageinfo = page.get("imageinfo", [])
            if not imageinfo:
                continue

            info = imageinfo[0]
            meta = info.get("extmetadata", {})
            license_name = meta.get("LicenseShortName", {}).get("value", "")
            usage_terms = meta.get("UsageTerms", {}).get("value", "")
            license_text = (license_name + " " + usage_terms).lower()

            if not any(word in license_text for word in ALLOWED_LICENSE_WORDS):
                continue

            image_url = info.get("thumburl") or info.get("url")
            if not image_url or not image_url.startswith("https://"):
                continue

            title = page.get("title", "Wikimedia Commons fayli")
            attribution = (
                f"Rasm manbasi: Wikimedia Commons — {title}\n"
                f"Litsenziya: {license_name or usage_terms or 'Commons metadata'}"
            )
            return {"url": image_url, "caption": attribution}

    except Exception as error:
        print(f"Rasm qidirishda xatolik ({search_term}): {error}")

    return None


def get_question_image(question):
    # Avval JSON ichidagi oldindan tekshirilgan URL ishlatiladi.
    image_url = question.get("image_url")
    if image_url:
        return {
            "url": image_url,
            "caption": question.get("image_credit", "Savol uchun rasm")
        }

    # image_search bo‘lsa Commons'dan litsenziyasi tekshirilgan rasm qidiriladi.
    search_term = question.get("image_search")
    if search_term:
        return search_commons_image(search_term)

    return None


def send_quiz(number, question):
    options = question["options"]
    correct_letter = question["answer"].strip().upper()
    letters = ["A", "B", "C", "D"]

    if correct_letter not in letters:
        raise ValueError(f"{number}-savolning javobi noto‘g‘ri")
    if len(options) != 4:
        raise ValueError(f"{number}-savolda 4 ta variant bo‘lishi kerak")

    data = {
        "chat_id": CHANNEL,
        "question": f"{number}. {question['question']}",
        "options": json.dumps(options, ensure_ascii=False),
        "type": "quiz",
        "correct_option_id": letters.index(correct_letter),
        "is_anonymous": "true",
        "allows_multiple_answers": "false"
    }

    if question.get("explanation"):
        data["explanation"] = question["explanation"]

    telegram("sendPoll", data)


def main():
    with open("questions.json", "r", encoding="utf-8") as file:
        questions = json.load(file)

    if len(questions) < TEST_COUNT:
        raise ValueError("Bazaga kamida 20 ta savol kerak")

    # Rasmli savollar tanlanish ehtimolini oshirish uchun:
    # avval mavjud rasmlari yoki image_search maydoni bor savollardan tanlaymiz.
    image_questions = [
        q for q in questions
        if q.get("image_url") or q.get("image_search")
    ]
    text_questions = [
        q for q in questions
        if not (q.get("image_url") or q.get("image_search"))
    ]

    selected = []
    if image_questions:
        selected.extend(random.sample(image_questions, min(5, len(image_questions))))

    remaining = TEST_COUNT - len(selected)
    pool = [q for q in questions if q not in selected]
    selected.extend(random.sample(pool, remaining))
    random.shuffle(selected)

    send_message(
        "🚘 ZIYODRIVE TEST\n\n"
        "Bugungi test boshlandi!\n"
        "20 ta savolga javob bering.\n"
        "Rasmli savollarda rasm savoldan oldin yuboriladi."
    )

    for number, question in enumerate(selected, 1):
        image = get_question_image(question)
        if image:
            try:
                send_photo(image["url"], image["caption"])
            except Exception as error:
                print(f"{number}-savol rasmi yuborilmadi: {error}")

        send_quiz(number, question)

    send_message(
        "🏁 ZIYODRIVE TEST YAKUNLANDI!\n\n"
        "Barcha 20 ta savol yuborildi.\n"
        "Faol qatnashganingiz uchun rahmat!"
    )
    print("Test muvaffaqiyatli yuborildi!")


if __name__ == "__main__":
    main()
