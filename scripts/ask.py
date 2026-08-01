import os
import sys
from letta_client import Letta
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/letta/.env"))

client = Letta(base_url="http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID")

query = " ".join(sys.argv[1:])
if not query.strip():
    print("Пустой запрос.")
    sys.exit(1)

response = client.agents.messages.create(
    agent_id=AGENT_ID,
    messages=[{"role": "user", "content": query}],
)

for msg in response.messages:
    if msg.message_type == "assistant_message":
        print(msg.content)
