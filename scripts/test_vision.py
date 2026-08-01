import os, base64
from letta_client import Letta
from dotenv import load_dotenv

load_dotenv()
client = Letta(base_url="http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID")

with open("/home/katya/DEV/bench/test.jpg", "rb") as f:
    img_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

response = client.agents.messages.create(
    agent_id=AGENT_ID,
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "Что на этой картинке?"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
        ],
    }],
)

for msg in response.messages:
    if msg.message_type == "assistant_message":
        print(msg.content)
