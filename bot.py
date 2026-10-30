
import os
import json
import random
import urllib.request
import urllib.parse

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL = "@ziyodrive"
TEST_COUNT = 20

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHANNEL,
        "text": text
    }).encode("utf-8")

    with urllib.request.urlopen(url, data=data) as response:
        result = json.loads(response.read().decode("utf-8"))

    if not result.get("ok"):
        raise RuntimeError("Telegram xabarni yubora olmadi")

def main():
    with open("questions.json", "r", encoding="utf-8") as file:
        questions = json.load(file)

    if len(questions) < TEST_COUNT:
        raise ValueError("Bazaga kamida 20 ta savol kerak")

    selected = random.sample(questions, TEST_COUNT)

    send_message(
        "🚘 ZIYODRIVE TEST\n\n"
        "Bugungi test: 20 ta savol!\n"
        "Bilimingizni sinab ko‘ring."
    )

    answers = []

    for i, q in enumerate(selected, 1):
        text = f"{i}. {q['question']}\n\n"
        for option in q["options"]:
            text += option + "\n"

        send_message(text)
        answers.append(f"{i}. {q['answer']}")

    send_message(
        "✅ TO‘G‘RI JAVOBLAR\n\n" + "\n".join(answers)
    )

if __name__ == "__main__":
    main()
