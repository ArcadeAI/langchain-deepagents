"""Arcade-aware tool definitions that execute existing connectors via arcade-py."""

from __future__ import annotations

import os
import textwrap
from dataclasses import dataclass
from typing import Iterable, Sequence

import arcadepy
from arcadepy import Arcade
from langchain_core.tools import tool
from typing_extensions import Annotated, Literal

DEFAULT_MODEL = os.getenv("ARCADE_MODEL", "gpt-4o-mini")
DEFAULT_SYSTEM_HINT = (
    "You are an Arcade automation runner. Call the requested connectors, take real actions, "
    "and return an audit log of what happened."
)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class ArcadeClientManager:
    """Shared helper that wraps the arcade-py client with safe fallbacks."""

    api_key: str | None = None
    base_url: str | None = None
    user_id: str | None = None
    model: str = DEFAULT_MODEL
    force_dry_run: bool | None = None
    wait_for_auth: bool | None = None
    system_hint: str = DEFAULT_SYSTEM_HINT

    def __post_init__(self) -> None:
        env_api_key = os.getenv("ARCADE_API_KEY")
        env_user = os.getenv("ARCADE_USER_ID")
        env_base = os.getenv("ARCADE_BASE_URL")

        self.api_key = self.api_key or env_api_key
        self.user_id = self.user_id or env_user
        self.base_url = self.base_url or env_base
        self.model = self.model or DEFAULT_MODEL

        if self.force_dry_run is None:
            self.force_dry_run = _env_bool("ARCADE_DRY_RUN", False)
        if self.wait_for_auth is None:
            self.wait_for_auth = _env_bool("ARCADE_WAIT_FOR_AUTH", False)

        self._client: Arcade | None = None
        if self.api_key and not self.force_dry_run:
            self._client = Arcade(api_key=self.api_key, base_url=self.base_url)

        self._dry_run_reason: str | None = None
        if self.force_dry_run:
            self._dry_run_reason = "ARCADE_DRY_RUN enabled"
        elif not self.api_key:
            self._dry_run_reason = "Missing ARCADE_API_KEY"
        elif not self.user_id:
            self._dry_run_reason = "Missing ARCADE_USER_ID"

    @property
    def is_live(self) -> bool:
        return (
            not self.force_dry_run
            and self._client is not None
            and self.user_id is not None
        )

    def configure(
        self,
        *,
        api_key: str | None = None,
        user_id: str | None = None,
        model: str | None = None,
        dry_run: bool | None = None,
    ) -> None:
        """Allow runtime reconfiguration (used by the CLI)."""
        if api_key is not None:
            self.api_key = api_key
        if user_id is not None:
            self.user_id = user_id
        if model is not None:
            self.model = model
        if dry_run is not None:
            self.force_dry_run = dry_run
        self.__post_init__()

    def _dry_run_message(self, prompt: str, tools: Sequence[str]) -> str:
        reason = self._dry_run_reason or "Client not fully configured"
        rendered_tools = ", ".join(tools)
        return textwrap.dedent(
            f"""\
            [DRY RUN] Arcade invocation blocked ({reason}).

            Planned prompt:
            {prompt.strip()}

            Intended tools: {rendered_tools}
            """
        ).strip()

    def _extract_connector_from_tool(self, tool_name: str) -> str:
        """Extract connector name from tool name (e.g., 'Jira.UpdateIssue' -> 'jira')."""
        if "." in tool_name:
            connector = tool_name.split(".")[0].lower()
            # Handle special cases
            if connector == "googlecalendar":
                return "google"
            return connector
        return "unknown"

    def execute_tool(
        self,
        *,
        tool_name: str,
        tool_input: dict[str, object],
    ) -> str:
        """Execute an Arcade tool directly using client.tools.execute()."""
        if not self.is_live:
            return self._dry_run_message(
                f"Execute {tool_name} with input: {tool_input}",
                [tool_name],
            )

        assert self._client is not None  # nosec - guarded by is_live

        # Execute the tool directly - let it fail naturally if authorization is needed
        try:
            response = self._client.tools.execute(
                tool_name=tool_name,
                input=tool_input,
                user_id=self.user_id,
            )
            output_value = getattr(response.output, "value", None)
            if output_value is not None:
                return str(output_value)
            return f"Tool {tool_name} executed successfully."
        except arcadepy.APIStatusError as exc:  # type: ignore[attr-defined]
            error_msg = exc.body or exc.message if hasattr(exc, "body") else str(exc)
            status_code = getattr(exc, "status_code", None)
            
            # Check if this is an authorization error (401 Unauthorized or 403 Forbidden)
            if status_code in (401, 403) or "authorization" in str(error_msg).lower() or "unauthorized" in str(error_msg).lower() or "forbidden" in str(error_msg).lower():
                connector = self._extract_connector_from_tool(tool_name)
                return (
                    f"Authorization required for {tool_name}. "
                    f"Please run: `uv run python cli.py authorize {connector}` "
                    f"to get the authorization URL and complete the flow."
                )
            
            return (
                f"Arcade API call failed ({status_code}): {error_msg}. "
                "If this is an authorization issue, run `uv run python cli.py authorize <connector>` and retry."
            )
        except (arcadepy.APIError, arcadepy.APIConnectionError) as exc:  # type: ignore[attr-defined]
            return f"Arcade API call failed: {exc}"


_ARCADE_MANAGER = ArcadeClientManager()


def configure_arcade_manager(**kwargs: object) -> None:
    """Allow other modules (e.g., CLI) to reconfigure the shared manager."""
    global _ARCADE_MANAGER
    _ARCADE_MANAGER.configure(**kwargs)


def get_arcade_manager() -> ArcadeClientManager:
    return _ARCADE_MANAGER


def _parse_tool_override(tool_names: str | None, fallback: Sequence[str]) -> list[str]:
    if not tool_names:
        return list(fallback)
    parsed = [name.strip() for name in tool_names.split(",") if name.strip()]
    return parsed or list(fallback)


@tool(parse_docstring=True)
def arcade_ticket_tool(
    action: Literal["create", "update", "comment", "lookup"],
    details: str | None = None,
    project_key: str | None = None,
    issue_key: str | None = None,
    priority: Literal["auto", "lowest", "low", "medium", "high", "highest"] = "auto",
    tool_names: Annotated[str | None, "Comma separated Arcade tool names"] = None,
) -> str:
    """Create, update, or comment on Jira issues via Arcade connectors.

    Args:
        action: Ticket intent (create, update, comment, or lookup).
        details: Natural language description of the desired change (required for create/update/comment, optional for lookup).
        project_key: Project identifier (e.g., JIRA project key).
        issue_key: Existing issue identifier when updating/commenting/looking up.
        priority: Desired ticket priority (auto lets Arcade decide).
        tool_names: Override the connector tools (default uses Jira helpers).
    """
    default_tools = {
        "create": "Jira.CreateIssue",
        "update": "Jira.UpdateIssue",
        "comment": "Jira.AddCommentToIssue",
        "lookup": "Jira.GetIssueById",  # Default, but will change based on inputs
    }
    
    # Build structured input based on action
    tool_input: dict[str, object] = {}
    tool_name = tool_names.split(",")[0].strip() if tool_names else None
    
    if action == "update":
        if not issue_key:
            return f"Cannot update Jira issue: 'issue_key' is required. Details: {details}"
        tool_name = tool_name or "Jira.UpdateIssue"
        tool_input["issue"] = issue_key
        if priority != "auto":
            tool_input["priority"] = priority
        if details:
            # For update, details can be description or title - assume description for now
            tool_input["description"] = details
    elif action == "create":
        if not project_key:
            return f"Cannot create Jira issue: 'project_key' is required. Details: {details}"
        tool_name = tool_name or "Jira.CreateIssue"
        tool_input["project"] = project_key
        if details:
            # Jira.CreateIssue requires 'title', not 'summary'
            tool_input["title"] = details
        if priority != "auto":
            tool_input["priority"] = priority
    elif action == "comment":
        if not issue_key:
            return f"Cannot comment on Jira issue: 'issue_key' is required. Details: {details}"
        tool_name = tool_name or "Jira.AddCommentToIssue"
        tool_input["issue"] = issue_key
        if details:
            # Jira.AddCommentToIssue uses 'body', not 'comment'
            tool_input["body"] = details
        else:
            return f"Cannot add comment: 'details' (comment text) is required for issue {issue_key}"
    elif action == "lookup":
        if issue_key:
            # Single issue lookup - use GetIssueById
            tool_name = tool_name or "Jira.GetIssueById"
            tool_input["issue"] = issue_key
        elif project_key:
            # List issues for a project - use ListIssues
            tool_name = tool_name or "Jira.ListIssues"
            tool_input["project"] = project_key
        elif details:
            # Check if details looks like a JQL query (contains keywords like '=', 'AND', 'OR', 'project', 'key')
            jql_indicators = ["=", "AND", "OR", "project", "key", "status", "assignee", "priority"]
            is_jql = any(indicator in details.upper() for indicator in jql_indicators)
            if is_jql:
                # Use SearchIssuesWithJql for JQL queries
                tool_name = tool_name or "Jira.SearchIssuesWithJql"
                tool_input["jql"] = details
            else:
                # Use SearchIssuesWithoutJql for natural language search
                tool_name = tool_name or "Jira.SearchIssuesWithoutJql"
                tool_input["keywords"] = details
        else:
            return (
                f"Cannot search Jira issues: provide either 'issue_key', 'project_key', "
                f"or 'details' (as a JQL query or search term)."
            )

    manager = get_arcade_manager()
    return manager.execute_tool(tool_name=tool_name, tool_input=tool_input)


@tool(parse_docstring=True)
def arcade_email_tool(
    recipient: str,
    subject: str,
    body: str,
    send_immediately: bool = True,
    cc: str | None = None,
    bcc: str | None = None,
    provider: Literal["google"] = "google",
    tool_names: Annotated[str | None, "Comma separated Arcade tool names"] = None,
) -> str:
    """Draft or send an email via Gmail using Arcade.

    Args:
        recipient: Primary recipient email address.
        subject: Email subject line.
        body: Email body content.
        send_immediately: If False, only draft the message.
        cc: Optional comma-separated CC emails.
        bcc: Optional comma-separated BCC emails.
        provider: Reserved for future support (currently Google only).
        tool_names: Override Arcade tool names (default per provider).
    """
    provider_tool_map = {
        "google": "Gmail.SendEmail",
    }
    tool_name = tool_names.split(",")[0].strip() if tool_names else provider_tool_map[provider]

    tool_input: dict[str, object] = {
        "recipient": recipient,
        "subject": subject,
        "body": body,
    }
    if cc:
        # Convert comma-separated string to array if needed
        tool_input["cc"] = [c.strip() for c in cc.split(",")] if isinstance(cc, str) else cc
    if bcc:
        # Convert comma-separated string to array if needed
        tool_input["bcc"] = [b.strip() for b in bcc.split(",")] if isinstance(bcc, str) else bcc

    manager = get_arcade_manager()
    return manager.execute_tool(tool_name=tool_name, tool_input=tool_input)


@tool(parse_docstring=True)
def arcade_multi_tool(
    tool_name: str,
    tool_input: str,
) -> str:
    """Execute any Arcade tool directly by name with JSON input.

    Args:
        tool_name: The Arcade tool name (e.g., "Jira.UpdateIssue", "Gmail.SendEmail").
        tool_input: JSON string with the tool's input parameters.
    """
    import json

    try:
        parsed_input = json.loads(tool_input)
    except json.JSONDecodeError as e:
        return f"Invalid JSON input: {e}. Expected a JSON object string."

    manager = get_arcade_manager()
    return manager.execute_tool(tool_name=tool_name, tool_input=parsed_input)

