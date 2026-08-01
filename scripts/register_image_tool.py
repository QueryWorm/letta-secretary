import os
from letta_client import Letta
from dotenv import load_dotenv

load_dotenv()
client = Letta(base_url="http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID")

with open("describe_image_tool.py") as f:
    source_code = f.read()

tool = client.tools.create(source_code=source_code)
client.agents.tools.attach(agent_id=AGENT_ID, tool_id=tool.id)
print("Attached:", tool.id, tool.name)
