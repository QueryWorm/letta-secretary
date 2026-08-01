from letta_client import Letta

client = Letta(base_url="http://localhost:8283")

agent = client.agents.create(
    name="igor_secretary",
    model="groq/llama-3.3-70b-versatile",
    embedding="letta/letta-free",
    memory_blocks=[
        {"label": "human", "value": "Игорь — технический специалист, работает с Excel/Sheets, пентестом, Linux."},
        {"label": "persona", "value": "Я — личный ассистент Игоря, помню контекст между разговорами."},
    ],
)

print("AGENT_ID:", agent.id)
