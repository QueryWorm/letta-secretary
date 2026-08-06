import json
import os
import re
import urllib.request

import yaml
from dotenv import load_dotenv
from letta_client import Letta

load_dotenv()
client = Letta(base_url="http://localhost:8283")

with open("agent_config.yaml") as f:
    config = yaml.safe_load(f)

AGENT_ID = config["agent_id"]
BUILTIN_TOOLS = {
    "send_message", "memory_replace", "memory_insert", "memory_rethink",
    "conversation_search", "archival_memory_search", "archival_memory_insert",
}

def tool_name_from_source(path):
    with open(path) as f:
        source = f.read()
    match = re.search(r"^def (\w+)\(", source, re.MULTILINE)
    return match.group(1), source

# --- Model ---
agent = client.agents.retrieve(agent_id=AGENT_ID)
if agent.llm_config.handle != config["model"]:
    print(f"Model mismatch: {agent.llm_config.handle} -> {config['model']}, updating...")
    client.agents.update(agent_id=AGENT_ID, model=config["model"])
else:
    print(f"Model OK: {config['model']}")

# --- Context window + compaction (via raw API; letta_client lacks these fields) ---
agent_id = AGENT_ID
desired_cwl = config.get("context_window_limit")
desired_cs = config.get("compaction_settings")
req = urllib.request.Request(
    f"http://localhost:8283/v1/agents/{agent_id}",
    headers={"Authorization": f"Bearer {os.environ['LETTA_API_KEY']}", "Content-Type": "application/json"},
)
state = json.load(urllib.request.urlopen(req, timeout=15))
current_cwl = (state.get("llm_config") or {}).get("context_window")
current_cs = state.get("compaction_settings") or {}
patch = {}
if desired_cwl is not None and current_cwl != desired_cwl:
    print(f"context_window_limit: {current_cwl} -> {desired_cwl}, updating...")
    patch["context_window_limit"] = desired_cwl
else:
    print(f"context_window_limit OK: {current_cwl}")
if desired_cs is not None:
    current_cs_model = current_cs.get("model")
    if isinstance(current_cs_model, dict):
        current_cs_model = current_cs_model.get("model")
    if current_cs_model != desired_cs.get("model"):
        print(f"compaction model: {current_cs_model} -> {desired_cs.get('model')}, updating...")
        patch["compaction_settings"] = desired_cs
    else:
        print(f"compaction model OK: {current_cs_model}")
else:
    print("compaction_settings not set in config")
if patch:
    data = json.dumps(patch).encode()
    req = urllib.request.Request(
        f"http://localhost:8283/v1/agents/{agent_id}",
        data=data,
        method="PATCH",
        headers={"Authorization": f"Bearer {os.environ['LETTA_API_KEY']}", "Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=15)

# --- Memory blocks ---
for label, desired_value in config["memory"].items():
    desired_value = desired_value.strip()
    current = client.agents.blocks.retrieve(agent_id=AGENT_ID, block_label=label)
    if current.value.strip() != desired_value:
        print(f"Memory block '{label}' differs, updating...")
        client.agents.blocks.update(agent_id=AGENT_ID, block_label=label, value=desired_value)
    else:
        print(f"Memory block '{label}' OK")

# --- Custom tools ---
desired_tools = {}
for entry in config["custom_tools"]:
    name, source = tool_name_from_source(entry["path"])
    desired_tools[name] = source

attached = client.agents.tools.list(agent_id=AGENT_ID)
attached_custom = {t.name: t for t in attached if t.name not in BUILTIN_TOOLS}

# Detach tools that are attached but not in config
for name, tool in attached_custom.items():
    if name not in desired_tools:
        print(f"Detaching stale tool: {name}")
        client.agents.tools.detach(agent_id=AGENT_ID, tool_id=tool.id)

# Attach/update tools from config
for name, source in desired_tools.items():
    existing = attached_custom.get(name)
    if existing is None:
        print(f"Attaching new tool: {name}")
        tool = client.tools.create(source_code=source)
        client.agents.tools.attach(agent_id=AGENT_ID, tool_id=tool.id)
    else:
        print(f"Tool '{name}' already attached (source diff not checked yet)")

print("Done.")
