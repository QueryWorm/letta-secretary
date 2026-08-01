import os
from letta_client import Letta
from dotenv import load_dotenv

load_dotenv()

client = Letta(base_url="http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID")

response = client.agents.messages.create(
    agent_id=AGENT_ID,
    messages=[{"role": "user", "content": "Какая сегодня погода в Харькове? Используй веб-поиск."}],
)

for msg in response.messages:
    print(msg.message_type, "-", getattr(msg, "content", None) or getattr(msg, "tool_call", None) or getattr(msg, "tool_return", None))
