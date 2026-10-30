
import os
import json
import random
import time
import urllib.request
import urllib.parse
import urllib.error

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL = "@ziyodrive"
TEST_COUNT = 20

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"


def telegram(method, data):
    url = API_URL + method
    payload = urllib.parse.urlencode(data).encode("utf-8")

    for attempt in range(6):
        try:
            request = urllib.request.Request(url, data=payload)

            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))

            if not result.get("ok"):
                raise RuntimeError(result.get("description", "Telegram xatosi"))

            time.sleep(2)
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


def send_message(text):
    telegram("sendMessage", {
        "chat_id": CHANNEL,
        "text": text
    })


def send_photo(image_url):
    telegram("sendPhoto", {
        "chat_id": CHANNEL,
        "photo": image_url
    })


def send_quiz(number, question):
    options = question["options"]
    correct_letter = question["answer"].strip().upper()

    letters = ["A", "B", "C", "D"]

    if correct_letter not in letters:
        raise ValueError(f"{number}-savolning javobi noto‘g‘ri")

    if len(options) != 4:
        raise ValueError(f"{number}-savolda 4 ta variant bo‘lishi kerak")

    correct_index = letters.index(correct_letter)

    data = {
        "chat_id": CHANNEL,
        "question": f"{number}. {question['question']}",
        "options": json.dumps(options, ensure_ascii=False),
        "type": "quiz",
        "correct_option_id": correct_index,
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

    selected = random.sample(questions, TEST_COUNT)

    send_message(
        "🚘 ZIYODRIVE TEST\n\n"
        "Bugungi test boshlandi!\n"
        "20 ta savolga javob bering.\n"
        "Har bir savolda to‘g‘ri javobni darhol bilib olasiz."
    )

    for number, question in enumerate(selected, 1):
        image_url = question.get("image_url")

        if image_url:
            send_photo(image_url)

        send_quiz(number, question)

    send_message(
        "🏁 ZIYODRIVE TEST YAKUNLANDI!\n\n"
        "Barcha 20 ta savol yuborildi.\n"
        "Faol qatnashganingiz uchun rahmat!"
    )

    print("Test muvaffaqiyatli yuborildi!")


if __name__ == "__main__":
    main()
