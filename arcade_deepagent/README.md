# 🛠️ Arcade Automation Quickstart

This quickstart demonstrates how to build a **tier-1 service-desk deepagent** that executes real Jira, Slack, Gmail, and Google Calendar workflows through [Arcade](https://docs.arcade.dev). While the [Deep Research](../deep_research) quickstart focuses on web research and synthesis, this agent focuses on **action-oriented automation**—manipulating tickets, sending updates, and scheduling follow-ups.

## 🧠 Understanding Deep Agents

Before diving into this quickstart, it's helpful to understand what makes a "deep agent" different from a simple tool-calling agent.

### The Deep Agent Architecture

The [`deepagents`](../../libs/deepagents) library implements four key capabilities that enable agents to handle complex, multi-step tasks:

```
┌─────────────────────────────────────────────────────────────────┐
│                         Deep Agent                              │
├─────────────────────────────────────────────────────────────────┤
│  1. PLANNING TOOL (write_todos)                                 │
│     Break complex tasks into trackable steps                    │
├─────────────────────────────────────────────────────────────────┤
│  2. FILESYSTEM (ls, read_file, write_file, edit_file)           │
│     Offload context to memory, prevent token overflow           │
├─────────────────────────────────────────────────────────────────┤
│  3. SUB-AGENTS (task)                                           │
│     Spawn specialized agents for context isolation              │
├─────────────────────────────────────────────────────────────────┤
│  4. DETAILED PROMPTS                                            │
│     Domain-specific instructions that guide behavior            │
└─────────────────────────────────────────────────────────────────┘
```

These capabilities are implemented as **middleware** that automatically attaches to any agent created with `create_deep_agent()`:

| Middleware | Purpose | Tools Provided |
|------------|---------|----------------|
| `TodoListMiddleware` | Task planning and progress tracking | `write_todos` |
| `FilesystemMiddleware` | Context management and long-term memory | `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep` |
| `SubAgentMiddleware` | Delegate work to specialized sub-agents | `task` |

### How This Quickstart Uses Deep Agents

The Arcade automation agent leverages all four capabilities:

```python
# agent.py - Factory for the Arcade automation deepagent
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

agent = create_deep_agent(
    model=ChatOpenAI(model="gpt-4o-mini"),
    tools=[                           # 🔧 Domain-specific tools
        arcade_ticket_tool,
        arcade_email_tool,
        arcade_multi_tool,
    ],
    system_prompt=SERVICE_DESK_INSTRUCTIONS,  # 📝 Detailed prompts
    subagents=[{                      # 🤖 Specialized sub-agents
        "name": "ticket-specialist",
        "description": "Executes precise Jira updates",
        "system_prompt": TICKET_SPECIALIST_INSTRUCTIONS,
        "tools": [arcade_ticket_tool],
    }],
)
```

The `create_deep_agent()` function returns a **LangGraph graph** that you can interact with using all standard LangGraph patterns (streaming, human-in-the-loop, memory, Studio).

## 🔄 Comparison: Deep Research vs. Arcade Automation

Both quickstarts use the same `deepagents` library but are tailored for different use cases:

| Aspect | Deep Research | Arcade Automation |
|--------|---------------|-------------------|
| **Purpose** | Web research and synthesis | Service-desk workflow automation |
| **Primary Tools** | `tavily_search`, `think_tool` | `arcade_ticket_tool`, `arcade_email_tool`, `arcade_multi_tool` |
| **External APIs** | Tavily (web search) | Arcade (Jira, Gmail, Slack, Calendar) |
| **Sub-Agent Role** | Research specific topics in parallel | Execute precise ticket updates |
| **Output** | Research reports saved to `/final_report.md` | Audit trails saved to `/requests/activity_log.md` |
| **Model** | Claude Sonnet 4.5 | OpenAI GPT-4o-mini |
| **Workflow** | Plan → Research → Synthesize → Report | Capture → Plan → Execute → Log |

### Architecture Comparison

**Deep Research Agent:**
```
User Query
    ↓
Main Agent (orchestrator)
    ├── write_todos: Plan research tasks
    ├── write_file: Save request to /research_request.md
    ├── task: Delegate to research-agent sub-agents
    │       └── tavily_search + think_tool
    ├── write_file: Save to /final_report.md
    └── Response with citations
```

**Arcade Automation Agent:**
```
User Request
    ↓
Main Agent (service-desk coordinator)
    ├── write_todos: Plan automation steps
    ├── write_file: Save request to /requests/latest.md
    ├── arcade_ticket_tool: Create/update/lookup Jira issues
    ├── arcade_email_tool: Send Gmail notifications
    ├── task: Delegate to ticket-specialist for complex updates
    │       └── arcade_ticket_tool
    ├── write_file: Log to /requests/activity_log.md
    └── Response with ticket summary
```

### Tool Design Philosophy

**Deep Research** uses custom tools that wrap Tavily:
```python
@tool
def tavily_search(query: str, max_results: int = 1) -> str:
    """Search web, fetch full content, return as markdown."""
    results = tavily_client.search(query, max_results=max_results)
    # Fetches full webpage content, converts to markdown
    return formatted_results
```

**Arcade Automation** uses tools that wrap Arcade's hosted connectors:
```python
@tool
def arcade_ticket_tool(
    action: Literal["create", "update", "comment", "lookup"],
    issue_key: str | None = None,
    details: str | None = None,
) -> str:
    """Create, update, or lookup Jira issues via Arcade."""
    # Maps action to correct Arcade tool (Jira.CreateIssue, Jira.GetIssueById, etc.)
    return manager.execute_tool(tool_name=tool_name, tool_input=tool_input)
```

The key difference: Arcade tools are **pre-built and hosted**—you don't implement the Jira/Gmail/Slack logic yourself. You just call them through the `arcade-py` client.

## 📦 Project Layout

```
arcade_deepagent/
├── agent.py                # Deepagent factory (create_deep_agent call)
├── cli.py                  # Typer CLI for shell-based runs
├── langgraph.json          # Register graph for langgraph dev/studio
├── pyproject.toml          # Dependencies (arcade-py, deepagents, langchain-openai)
├── .env                    # API keys (ARCADE_API_KEY, OPENAI_API_KEY, etc.)
└── arcade_agent/
    ├── __init__.py
    ├── prompts.py          # SERVICE_DESK_INSTRUCTIONS, TICKET_SPECIALIST_INSTRUCTIONS
    └── tools.py            # ArcadeClientManager + LangChain tool wrappers
```

### Key Files Explained

**`agent.py`** - The entry point that creates the deep agent:
- Imports `create_deep_agent` from the `deepagents` library
- Configures OpenAI model (default: `gpt-4o-mini`)
- Registers Arcade tools and sub-agents
- Exports `agent` for LangGraph server

**`arcade_agent/tools.py`** - Wraps Arcade's hosted tools for LangChain:
- `ArcadeClientManager`: Manages the `arcade-py` client connection
- `arcade_ticket_tool`: Jira operations (create, update, comment, lookup)
- `arcade_email_tool`: Gmail sending via `Gmail.SendEmail`
- `arcade_multi_tool`: Generic tool for any Arcade connector

**`arcade_agent/prompts.py`** - Domain-specific instructions:
- `SERVICE_DESK_INSTRUCTIONS`: Main agent workflow (capture → plan → execute → log)
- `TICKET_SPECIALIST_INSTRUCTIONS`: Sub-agent for precise Jira updates

## ✅ Prerequisites

1. **Install [uv](https://docs.astral.sh/uv/)** - Fast Python package manager
2. **Get API Keys:**
   - `ARCADE_API_KEY` – [Arcade dashboard](https://docs.arcade.dev/en/references/api)
   - `ARCADE_USER_ID` – Your identifier for connector authorization (e.g., email)
   - `OPENAI_API_KEY` – [OpenAI platform](https://platform.openai.com/api-keys)

## 🚀 Setup

```bash
# Navigate to this quickstart
cd deepagents-quickstarts/arcade_deepagent

# Install dependencies
uv sync

# Create .env file with your credentials
cat > .env << 'EOF'
ARCADE_API_KEY=arc_...
ARCADE_USER_ID=user@example.com
OPENAI_API_KEY=sk-...
EOF
```

## Usage Options

### Option 1: LangGraph Server (Recommended)

Run a local [LangGraph server](https://langchain-ai.github.io/langgraph/tutorials/langgraph-platform/local-server/) with Studio UI:

```bash
uv run langgraph dev
```

This opens the Studio interface at `http://127.0.0.1:2024` where you can:
- Submit automation tasks via chat
- Visualize the agent's planning and execution
- Inspect tool calls and sub-agent delegations

You can also connect to the [deepagents-ui](https://github.com/langchain-ai/deep-agents-ui):

```bash
git clone https://github.com/langchain-ai/deepagents-ui.git
cd deepagents-ui
yarn install
yarn dev
```

### Option 2: CLI

Run tasks directly from the command line:

```bash
# Execute a task
uv run python cli.py run "Escalate JIRA-123 to High and notify the team in Slack"

# Preview without executing (dry run)
uv run python cli.py dryrun "Create a new bug ticket for login issues"

# Authorize a connector (required before first use)
uv run python cli.py authorize jira
uv run python cli.py authorize google
uv run python cli.py authorize slack

# List available Arcade tools
uv run python cli.py tools
```

### Authorization Flow

Arcade connectors require OAuth authorization before use. When you first try to use a connector, you'll see:

```
Authorization required for Jira.CreateIssue.
Please run: `uv run python cli.py authorize jira` to complete the flow.
```

The `authorize` command will:
1. Generate an authorization URL
2. Wait for you to complete the OAuth flow in your browser
3. Confirm when authorization is complete

## 🔧 How Arcade Tools Work

Unlike Deep Research which implements custom tools, Arcade Automation uses **pre-built hosted tools** from Arcade's MCP servers:

### Available Arcade Connectors

| Connector | Tools Used | Purpose |
|-----------|------------|---------|
| **Jira** | `Jira.CreateIssue`, `Jira.UpdateIssue`, `Jira.GetIssueById`, `Jira.AddCommentToIssue`, `Jira.SearchIssuesWithJql` | Ticket management |
| **Gmail** | `Gmail.SendEmail` | Email notifications |
| **Slack** | `Slack.SendMessage` | Team chat updates |
| **Google Calendar** | `GoogleCalendar.CreateEvent` | Meeting scheduling |

### Tool Wrapper Architecture

The quickstart wraps Arcade tools with LangChain-compatible interfaces:

```python
# arcade_agent/tools.py

@tool
def arcade_ticket_tool(
    action: Literal["create", "update", "comment", "lookup"],
    details: str | None = None,
    issue_key: str | None = None,
    project_key: str | None = None,
) -> str:
    """Create, update, or lookup Jira issues via Arcade."""
    
    # Map action to correct Arcade tool
    if action == "lookup" and issue_key:
        tool_name = "Jira.GetIssueById"
        tool_input = {"issue": issue_key}
    elif action == "create":
        tool_name = "Jira.CreateIssue"
        tool_input = {"project": project_key, "title": details}
    # ... etc
    
    # Execute via arcade-py client
    return manager.execute_tool(tool_name=tool_name, tool_input=tool_input)
```

This abstraction lets the LLM work with a simpler interface while the tool handles mapping to the correct Arcade API calls.

## 🧩 Extending

### Custom Model

```python
from langchain_openai import ChatOpenAI
from langchain.chat_models import init_chat_model
from agent import create_agent

# Using OpenAI GPT-4o
model = ChatOpenAI(model="gpt-4o", temperature=0.0)

# Using Claude (requires langchain-anthropic)
model = init_chat_model(model="anthropic:claude-sonnet-4-5-20250929", temperature=0.0)

agent = create_agent(model_name="gpt-4o", temperature=0.0)
```

Or via environment variables:
```bash
export OPENAI_MODEL=gpt-4o
export ARCADE_AGENT_TEMPERATURE=0.0
```

### Custom Instructions

Modify `arcade_agent/prompts.py` to customize agent behavior:

| Instruction Set | Purpose |
|----------------|---------|
| `SERVICE_DESK_INSTRUCTIONS` | Main workflow: capture request → plan with TODOs → execute via Arcade → log outcomes |
| `TICKET_SPECIALIST_INSTRUCTIONS` | Sub-agent focus: precise Jira updates with action/reference/next-steps format |

### Custom Tools

Add new tools by wrapping additional Arcade connectors:

```python
# arcade_agent/tools.py

@tool
def arcade_slack_tool(
    channel: str,
    message: str,
) -> str:
    """Send a message to a Slack channel."""
    manager = get_arcade_manager()
    return manager.execute_tool(
        tool_name="Slack.SendMessage",
        tool_input={"channel": channel, "text": message},
    )
```

Then register in `agent.py`:
```python
agent = create_deep_agent(
    model=model,
    tools=[arcade_ticket_tool, arcade_email_tool, arcade_slack_tool],
    # ...
)
```

### Adding Sub-Agents

Create specialized sub-agents for different domains:

```python
# agent.py

def _build_subagents():
    return [
        {
            "name": "ticket-specialist",
            "description": "Executes precise Jira updates",
            "system_prompt": TICKET_SPECIALIST_INSTRUCTIONS,
            "tools": [arcade_ticket_tool],
        },
        {
            "name": "communications-specialist", 
            "description": "Handles Slack and email notifications",
            "system_prompt": COMMS_INSTRUCTIONS,
            "tools": [arcade_email_tool, arcade_slack_tool],
        },
    ]
```

## 📚 Resources

- **[Deepagents Library](../../libs/deepagents/README.md)** - Core library documentation
- **[Deep Research Quickstart](../deep_research/README.md)** - Compare with research-focused agent
- **[Arcade Documentation](https://docs.arcade.dev)** - Full Arcade API reference
- **[arcade-py GitHub](https://github.com/ArcadeAI/arcade-py)** - Python client for Arcade
- **[LangGraph Docs](https://langchain-ai.github.io/langgraph/)** - Agent orchestration framework
- **[Deep Research Course](https://academy.langchain.com/courses/deep-research-with-langgraph)** - Full course on deep agents

## 🔍 Troubleshooting

### "ModuleNotFoundError: No module named 'deepagents'"

Run LangGraph with the virtual environment:
```bash
uv run langgraph dev  # Not just `langgraph dev`
```

### "Authorization required for [tool]"

Complete the OAuth flow:
```bash
uv run python cli.py authorize jira
uv run python cli.py authorize google
uv run python cli.py authorize slack
```

### "400 Bad Request" from Arcade

Check that you're using the correct tool names and parameters. The Arcade API is strict about parameter names (e.g., `recipient` not `to` for Gmail, `body` not `comment` for Jira comments).

### Environment Variables Not Loading

Ensure `.env` is in the `arcade_deepagent` directory and run commands from that directory:
```bash
cd deepagents-quickstarts/arcade_deepagent
uv run python cli.py run "your task"
```
