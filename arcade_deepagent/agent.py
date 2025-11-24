"""Factory for the Arcade automation deepagent."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, List

from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

from arcade_agent.prompts import (
    SERVICE_DESK_INSTRUCTIONS,
    TICKET_SPECIALIST_INSTRUCTIONS,
)
from arcade_agent.tools import (
    arcade_email_tool,
    arcade_multi_tool,
    arcade_ticket_tool,
)

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_TEMPERATURE = float(os.getenv("ARCADE_AGENT_TEMPERATURE", "0.0"))
CURRENT_DATE = datetime.now().strftime("%Y-%m-%d")


def _build_subagents() -> List[dict[str, Any]]:
    return [
        {
            "name": "ticket-specialist",
            "description": "Executes precise Jira updates and summarizes the results.",
            "system_prompt": TICKET_SPECIALIST_INSTRUCTIONS.format(date=CURRENT_DATE),
            "tools": [arcade_ticket_tool],
        }
    ]


def create_agent(
    *,
    model_name: str | None = None,
    temperature: float | None = None,
):
    """Create the Arcade automation agent with configured tools and prompts."""
    resolved_model = model_name or DEFAULT_MODEL
    resolved_temp = DEFAULT_TEMPERATURE if temperature is None else temperature
    model = ChatOpenAI(model=resolved_model, temperature=resolved_temp)

    return create_deep_agent(
        model=model,
        tools=[
            arcade_ticket_tool,
            arcade_email_tool,
            arcade_multi_tool,
        ],
        system_prompt=SERVICE_DESK_INSTRUCTIONS,
        subagents=_build_subagents(),
    )


# Convenience export so `from agent import agent` mirrors other quickstarts.
agent = create_agent()

