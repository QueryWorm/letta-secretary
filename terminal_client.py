import os
from letta_client import Letta
from dotenv import load_dotenv

load_dotenv()

client = Letta(base_url="http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID")

print("Терминальный клиент Letta. Ctrl+C для выхода.\n")

while True:
    try:
        user_input = input("Ты: ")
    except (EOFError, KeyboardInterrupt):
        print("\nВыход.")
        break

    if not user_input.strip():
        continue

    response = client.agents.messages.create(
        agent_id=AGENT_ID,
        messages=[{"role": "user", "content": user_input}],
    )

    for msg in response.messages:
        if msg.message_type == "assistant_message":
            print(f"Агент: {msg.content}\n")
