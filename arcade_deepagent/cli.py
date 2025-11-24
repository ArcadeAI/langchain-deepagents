"""CLI entry point for the Arcade automation quickstart."""

from __future__ import annotations

import json
import os
from typing import Optional

import typer
from arcadepy import Arcade
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

DEFAULT_TOOL_LIST = [
    "Jira.CreateIssue",
    "Jira.UpdateIssue",
    "Jira.AddCommentToIssue",
    "Jira.GetIssueById",
    "Jira.SearchIssuesWithJql",
    "Jira.SearchIssuesWithoutJql",
    "Jira.ListIssues",
    "Gmail.SendEmail",
    "GoogleCalendar.CreateEvent",
    "Slack.SendMessage",
]

load_dotenv()

from agent import create_agent  # noqa: E402
from arcade_agent.tools import (  # noqa: E402
    arcade_multi_tool,
    configure_arcade_manager,
    get_arcade_manager,
)

app = typer.Typer(help="Run the Arcade automation deepagent from the terminal.")
console = Console()


def _invoke_agent(task: str) -> dict:
    agent = create_agent()
    inputs = {"messages": [{"role": "user", "content": task}]}
    return agent.invoke(inputs)


def _render_result(result: dict) -> None:
    messages = result.get("messages", [])
    if not messages:
        console.print("[bold red]Agent returned no messages[/bold red]")
        return
    last_message = messages[-1]
    content = getattr(last_message, "content", str(last_message))
    if isinstance(content, list):
        content = "\n".join(
            block.get("text", json.dumps(block)) for block in content if isinstance(block, dict)
        )
    console.print(Panel.fit(content, title="🤖 Agent Response", border_style="green"))


def _require_api_key() -> str:
    api_key = os.getenv("ARCADE_API_KEY")
    if not api_key:
        raise typer.BadParameter("Set ARCADE_API_KEY in your environment or .env file.")
    return api_key


def _require_user_id(user_id: Optional[str]) -> str:
    resolved = user_id or os.getenv("ARCADE_USER_ID")
    if not resolved:
        raise typer.BadParameter("Provide --user-id or set ARCADE_USER_ID.")
    return resolved


@app.command()
def run(
    task: str = typer.Argument(..., help="Natural-language task for the agent to execute."),
    api_key: Optional[str] = typer.Option(None, help="Override ARCADE_API_KEY for this run."),
    user_id: Optional[str] = typer.Option(None, help="Override ARCADE_USER_ID for this run."),
    model: Optional[str] = typer.Option(None, help="Override arcade completion model (default gpt-4o-mini)."),
    dry_run: bool = typer.Option(False, help="Force dry-run mode to preview prompts without executing connectors."),
) -> None:
    """Invoke the deepagent on a one-off task."""
    if any([api_key, user_id, model]) or dry_run:
        configure_arcade_manager(
            api_key=api_key,
            user_id=user_id,
            model=model,
            dry_run=dry_run,
        )
    result = _invoke_agent(task)
    _render_result(result)


@app.command("dryrun")
def dry_run(
    task: str = typer.Argument(..., help="Task to preview without executing real connectors."),
) -> None:
    """Preview the underlying Arcade call without taking action."""
    configure_arcade_manager(dry_run=True)
    result = _invoke_agent(task)
    _render_result(result)


@app.command("tools")
def list_tools() -> None:
    """Show the Arcade tool names the wrappers invoke."""
    rendered = "\n".join(f"- {name}" for name in DEFAULT_TOOL_LIST)
    console.print(Panel(rendered, title="Arcade Tool Inventory"))


def _connector_to_tool_name(connector: str) -> str:
    """Map connector name to a representative tool name for authorization."""
    connector_lower = connector.lower()
    tool_map = {
        "jira": "Jira.UpdateIssue",
        "google": "Gmail.SendEmail",
        "gmail": "Gmail.SendEmail",
        "slack": "Slack.SendMessage",
        "calendar": "GoogleCalendar.CreateEvent",
        "googlecalendar": "GoogleCalendar.CreateEvent",
    }
    return tool_map.get(connector_lower, f"{connector.capitalize()}.UpdateIssue")


@app.command()
def authorize(
    connector: str = typer.Argument(..., help="Connector slug, e.g., 'google', 'jira', 'slack'."),
    tool_name: Optional[str] = typer.Option(
        None,
        help="Specific tool name to authorize (overrides connector mapping).",
    ),
    user_id: Optional[str] = typer.Option(
        None,
        help="Override ARCADE_USER_ID for this authorization request.",
    ),
) -> None:
    """Kick off an Arcade connector authorization flow using tool-based auth."""
    api_key = _require_api_key()
    resolved_user = _require_user_id(user_id)
    client = Arcade(api_key=api_key, base_url=os.getenv("ARCADE_BASE_URL"))
    
    # Use provided tool name or map connector to a representative tool
    target_tool = tool_name or _connector_to_tool_name(connector)
    
    try:
        response = client.tools.authorize(
            tool_name=target_tool,
            user_id=resolved_user,
        )
        status = getattr(response, "status", "unknown")
        auth_url = getattr(response, "url", None)
        auth_id = getattr(response, "id", None)

        console.print(f"Authorization status: [bold]{status}[/bold]")
        if auth_url and status != "completed":
            console.print(f"\n[bold green]Complete the flow here:[/bold green]")
            console.print(f"[link={auth_url}]{auth_url}[/link]")
            if auth_id:
                console.print(f"\nWaiting for authorization to complete...")
                try:
                    client.auth.wait_for_completion(auth_id)
                    console.print("[bold green]✓ Authorization completed![/bold green]")
                except Exception as wait_err:
                    console.print(f"[yellow]Note: Could not auto-wait for completion: {wait_err}[/yellow]")
                    console.print("Please complete the authorization in your browser and retry your command.")
        elif status == "completed":
            console.print("[bold green]Connector already authorized.[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Authorization failed:[/bold red] {e}")
        console.print(f"\nTried to authorize tool: [bold]{target_tool}[/bold]")
        console.print("You can specify a different tool with: --tool-name <ToolName.Action>")


def main() -> None:
    app()


if __name__ == "__main__":
    main()

