import os
from letta_client import Letta
from dotenv import load_dotenv

load_dotenv()

client = Letta(base_url="http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID")

tools = client.agents.tools.list(agent_id=AGENT_ID)
for t in tools:
    if t.name == "web_search":
        client.agents.tools.detach(agent_id=AGENT_ID, tool_id=t.id)
        print("Detached:", t.id, t.name)

with open("web_search_tool.py") as f:
    source_code = f.read()

tool = client.tools.create(source_code=source_code)
client.agents.tools.attach(agent_id=AGENT_ID, tool_id=tool.id)
print("Attached:", tool.id, tool.name)
