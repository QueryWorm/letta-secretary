import os
from letta_client import Letta
from dotenv import load_dotenv

load_dotenv()

client = Letta(base_url="http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID")

response = client.agents.messages.create(
    agent_id=AGENT_ID,
    messages=[{"role": "user", "content": "Привет! Запомни — меня зовут Игорь, я из Харькова."}],
)

for msg in response.messages:
    print(msg)
