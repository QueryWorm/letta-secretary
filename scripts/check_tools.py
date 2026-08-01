import os
from letta_client import Letta
from dotenv import load_dotenv

load_dotenv()

client = Letta(base_url="http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID")

tools = client.agents.tools.list(agent_id=AGENT_ID)
for t in tools:
    print(t.id, "-", t.name)
