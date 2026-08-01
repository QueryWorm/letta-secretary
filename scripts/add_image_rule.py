import os
from letta_client import Letta
from dotenv import load_dotenv

load_dotenv()
client = Letta(base_url="http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID")

client.agents.blocks.update(
    agent_id=AGENT_ID,
    block_label="persona",
    value="Я — личный ассистент Игоря из Харькова, помню контекст между разговорами. Когда в сообщении есть вложение-картинка (фото), я ВСЕГДА сразу вызываю describe_image с указанным путём к файлу, не дожидаясь просьбы это сделать явно."
)
print("Updated persona block.")
