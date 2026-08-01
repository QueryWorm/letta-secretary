import os
from letta_client import Letta
from dotenv import load_dotenv

load_dotenv()
client = Letta(base_url="http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID")

path = "/tmp/lettabot/attachments/whatsapp/95727019622632_lid/2026-07-31T06-31-43-855Z-eb5252dc-whatsapp-3EB01009079255AE4AE278.jpeg"

response = client.agents.messages.create(
    agent_id=AGENT_ID,
    messages=[{"role": "user", "content": f"Используй инструмент describe_image, чтобы посмотреть на файл {path}. Опиши что там."}],
)

for msg in response.messages:
    print(msg.message_type, "-", getattr(msg, "content", None) or getattr(msg, "tool_call", None) or getattr(msg, "tool_return", None))
