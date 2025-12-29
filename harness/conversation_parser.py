"""
Parse Claude Code conversation logs from JSONL files.

Claude Code stores conversation logs in ~/.claude/projects/<project-path>/
Each conversation is stored as a .jsonl file with one JSON object per line.

This module extracts accurate metrics from these logs including:
- Token usage (input, output, cache)
- Tool usage (MCP calls, Skill invocations)
- Conversation statistics (messages, turns)
- Invar protocol adherence (Check-In, Final)
"""

import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ConversationMetrics:
    """Metrics extracted from a Claude conversation log."""

    # Token usage
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    # Conversation stats
    assistant_messages: int = 0
    user_messages: int = 0
    total_turns: int = 0  # Number of complete user->assistant exchanges

    # Tool usage
    tool_uses: dict[str, int] = field(default_factory=dict)
    total_tool_calls: int = 0

    # MCP-specific
    mcp_calls: dict[str, int] = field(default_factory=dict)
    total_mcp_calls: int = 0

    # Skill invocations
    skill_calls: int = 0

    # Invar protocol adherence
    has_checkin: bool = False
    has_final: bool = False
    final_status: str = ""  # "PASS" or "FAIL"

    # Time tracking
    first_message_time: str = ""
    last_message_time: str = ""

    # Message content (for conversation preservation)
    messages: list[dict] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        """Total tokens including cache."""
        return (
            self.input_tokens +
            self.output_tokens +
            self.cache_creation_tokens +
            self.cache_read_tokens
        )

    @property
    def billable_tokens(self) -> int:
        """Tokens that count toward billing (excluding cache reads)."""
        return self.input_tokens + self.output_tokens + self.cache_creation_tokens

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "total_tokens": self.total_tokens,
            "billable_tokens": self.billable_tokens,
            "assistant_messages": self.assistant_messages,
            "user_messages": self.user_messages,
            "total_turns": self.total_turns,
            "tool_uses": self.tool_uses,
            "total_tool_calls": self.total_tool_calls,
            "mcp_calls": self.mcp_calls,
            "total_mcp_calls": self.total_mcp_calls,
            "skill_calls": self.skill_calls,
            "has_checkin": self.has_checkin,
            "has_final": self.has_final,
            "final_status": self.final_status,
            "first_message_time": self.first_message_time,
            "last_message_time": self.last_message_time,
            "messages": self.messages,
        }


def get_claude_projects_dir() -> Path:
    """Get the Claude projects directory."""
    return Path.home() / ".claude" / "projects"


def workspace_to_project_name(workspace: Path) -> str:
    """
    Convert a workspace path to Claude's project directory name.

    Claude converts paths like:
    /Users/tefx/Projects/invar-benchmark/workspace/treatment/task_201_pipeline
    to:
    -Users-tefx-Projects-invar-benchmark-workspace-treatment-task-201-pipeline
    """
    # Get absolute path
    abs_path = workspace.resolve()

    # Convert to Claude's format: replace / with - and _ with -
    path_str = str(abs_path)
    project_name = path_str.replace("/", "-").replace("_", "-")

    return project_name


def find_conversation_file(
    workspace: Path,
    start_time: str | None = None,
    end_time: str | None = None,
) -> Path | None:
    """
    Find the conversation file for a workspace within a time window.

    Args:
        workspace: Task workspace directory
        start_time: ISO timestamp - find file modified after this time
        end_time: ISO timestamp - find file modified before this time

    Returns:
        Path to the matching conversation JSONL file, or None if not found
    """
    from datetime import datetime

    projects_dir = get_claude_projects_dir()
    project_name = workspace_to_project_name(workspace)
    project_dir = projects_dir / project_name

    if not project_dir.exists():
        return None

    # Find all non-agent JSONL files (agent-* files are subagent logs)
    jsonl_files = [
        f for f in project_dir.glob("*.jsonl")
        if not f.name.startswith("agent-")
    ]

    if not jsonl_files:
        return None

    # If time window specified, filter files
    if start_time or end_time:
        filtered = []
        for f in jsonl_files:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)

            if start_time:
                try:
                    start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    # Remove timezone for comparison
                    start_dt = start_dt.replace(tzinfo=None)
                    if mtime < start_dt:
                        continue
                except ValueError:
                    pass

            if end_time:
                try:
                    end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                    end_dt = end_dt.replace(tzinfo=None)
                    # Add buffer for tasks that complete shortly after recorded end time
                    from datetime import timedelta
                    if mtime > end_dt + timedelta(minutes=5):
                        continue
                except ValueError:
                    pass

            filtered.append(f)

        if filtered:
            # Return the largest file in the time window (likely the main conversation)
            return max(filtered, key=lambda f: f.stat().st_size)

    # Fallback: return most recently modified file
    return max(jsonl_files, key=lambda f: f.stat().st_mtime)


def parse_conversation_file(filepath: Path) -> ConversationMetrics:
    """
    Parse a Claude conversation JSONL file and extract metrics.

    Args:
        filepath: Path to the .jsonl conversation file

    Returns:
        ConversationMetrics with extracted data
    """
    metrics = ConversationMetrics()
    tool_counts: Counter = Counter()
    mcp_counts: Counter = Counter()

    with open(filepath, 'r') as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                _process_log_entry(data, metrics, tool_counts, mcp_counts)
            except json.JSONDecodeError:
                continue

    # Finalize counters
    metrics.tool_uses = dict(tool_counts)
    metrics.total_tool_calls = sum(tool_counts.values())
    metrics.mcp_calls = dict(mcp_counts)
    metrics.total_mcp_calls = sum(mcp_counts.values())

    # Calculate turns (user->assistant pairs)
    metrics.total_turns = min(metrics.user_messages, metrics.assistant_messages)

    return metrics


def _process_log_entry(
    data: dict[str, Any],
    metrics: ConversationMetrics,
    tool_counts: Counter,
    mcp_counts: Counter,
) -> None:
    """Process a single log entry and update metrics."""
    entry_type = data.get('type', '')

    if entry_type == 'user':
        metrics.user_messages += 1
        timestamp = data.get('timestamp', '')
        if not metrics.first_message_time:
            metrics.first_message_time = timestamp
        metrics.last_message_time = timestamp

        # Extract user message content
        msg = data.get('message', {})
        content = msg.get('content', '')
        if isinstance(content, str) and content:
            metrics.messages.append({
                'role': 'user',
                'content': content[:5000],  # Truncate for storage
            })

    elif entry_type == 'assistant':
        metrics.assistant_messages += 1
        timestamp = data.get('timestamp', '')
        metrics.last_message_time = timestamp

        msg = data.get('message', {})
        usage = msg.get('usage', {})

        # Extract token usage
        metrics.input_tokens += usage.get('input_tokens', 0)
        metrics.output_tokens += usage.get('output_tokens', 0)
        metrics.cache_creation_tokens += usage.get('cache_creation_input_tokens', 0)
        metrics.cache_read_tokens += usage.get('cache_read_input_tokens', 0)

        # Process content blocks
        content = msg.get('content', [])
        text_parts = []
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue

                block_type = block.get('type', '')

                if block_type == 'tool_use':
                    tool_name = block.get('name', '')
                    tool_counts[tool_name] += 1

                    # Track MCP calls
                    if tool_name.startswith('mcp__'):
                        mcp_counts[tool_name] += 1

                    # Track Skill invocations
                    if tool_name == 'Skill':
                        metrics.skill_calls += 1

                elif block_type == 'text':
                    text = block.get('text', '')
                    text_parts.append(text)

                    # Check for Invar protocol markers (strict patterns)
                    # Check-In format: "✓ Check-In:" or "Check-In:" at line start
                    if re.search(r'^✓?\s*Check-In:', text, re.MULTILINE):
                        metrics.has_checkin = True

                    # Final format: "✓ Final:" or "Final:" followed by status
                    if re.search(r'^✓?\s*Final:', text, re.MULTILINE):
                        metrics.has_final = True
                        # Extract status from same line
                        final_match = re.search(r'^✓?\s*Final:.*?(PASS|FAIL)', text, re.MULTILINE | re.IGNORECASE)
                        if final_match:
                            metrics.final_status = final_match.group(1).upper()

        # Store assistant message content
        if text_parts:
            combined_text = '\n'.join(text_parts)
            metrics.messages.append({
                'role': 'assistant',
                'content': combined_text[:5000],  # Truncate for storage
            })


def parse_workspace_conversation(
    workspace: Path,
    start_time: str | None = None,
    end_time: str | None = None,
) -> ConversationMetrics | None:
    """
    Parse conversation metrics for a workspace.

    Args:
        workspace: Task workspace directory
        start_time: ISO timestamp - find file modified after this time
        end_time: ISO timestamp - find file modified before this time

    Returns:
        ConversationMetrics or None if no conversation found
    """
    filepath = find_conversation_file(workspace, start_time, end_time)
    if filepath is None:
        return None

    return parse_conversation_file(filepath)


def calculate_time_delta_seconds(
    start_iso: str,
    end_iso: str,
) -> float:
    """
    Calculate time difference in seconds between two ISO timestamps.

    Args:
        start_iso: Start timestamp in ISO format
        end_iso: End timestamp in ISO format

    Returns:
        Time difference in seconds
    """
    from datetime import datetime

    try:
        start = datetime.fromisoformat(start_iso.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_iso.replace('Z', '+00:00'))
        return (end - start).total_seconds()
    except (ValueError, TypeError):
        return 0.0
