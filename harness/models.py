"""
Data models for benchmark framework.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TaskTier(Enum):
    """Task difficulty/type tiers."""
    TIER1_STANDARD = "tier1_standard"
    TIER2_CONTRACTS = "tier2_contracts"
    TIER3_INTEGRATION = "tier3_integration"
    TIER4_SWE = "tier4_swe"  # SWE-bench tasks


class ExperimentGroup(Enum):
    """Experiment groups for A/B testing."""
    CONTROL = "control"      # Without Invar
    TREATMENT = "treatment"  # With Invar


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class SWEMetadata:
    """SWE-bench specific metadata."""
    instance_id: str = ""
    repo: str = ""  # e.g., "django/django"
    base_commit: str = ""
    test_patch: str = ""  # Test file patch
    gold_patch: str = ""  # Reference solution patch
    fail_to_pass: list[str] = field(default_factory=list)  # Tests that should pass after fix
    pass_to_pass: list[str] = field(default_factory=list)  # Regression tests
    version: str = ""
    environment_setup_commit: str = ""
    difficulty_score: int = 0  # Calculated: patch_lines + fail_tests*5 + pass_tests*0.1

    @property
    def calculated_difficulty_score(self) -> int:
        """Calculate difficulty score from patch size and test counts.

        Formula: patch_lines + fail_to_pass_count * 5 + pass_to_pass_count * 0.1
        - Patch lines: Direct measure of change complexity
        - Fail to pass: Tests to fix (weighted heavily)
        - Pass to pass: Regression risk (low weight)
        """
        patch_lines = len(self.gold_patch.splitlines()) if self.gold_patch else 0
        fail_count = len(self.fail_to_pass)
        pass_count = len(self.pass_to_pass)
        return int(patch_lines + fail_count * 5 + pass_count * 0.1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "repo": self.repo,
            "base_commit": self.base_commit,
            "test_patch": self.test_patch,
            "gold_patch": self.gold_patch,
            "fail_to_pass": self.fail_to_pass,
            "pass_to_pass": self.pass_to_pass,
            "version": self.version,
            "environment_setup_commit": self.environment_setup_commit,
            "difficulty_score": self.difficulty_score or self.calculated_difficulty_score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SWEMetadata":
        metadata = cls(
            instance_id=data.get("instance_id", ""),
            repo=data.get("repo", ""),
            base_commit=data.get("base_commit", ""),
            test_patch=data.get("test_patch", ""),
            gold_patch=data.get("gold_patch", ""),
            fail_to_pass=data.get("fail_to_pass", []),
            pass_to_pass=data.get("pass_to_pass", []),
            version=data.get("version", ""),
            environment_setup_commit=data.get("environment_setup_commit", ""),
            difficulty_score=data.get("difficulty_score", 0),
        )
        # Auto-calculate if not stored
        if not metadata.difficulty_score:
            metadata.difficulty_score = metadata.calculated_difficulty_score
        return metadata


@dataclass
class Task:
    """Represents a benchmark task."""
    id: str
    name: str
    description: str
    tier: TaskTier
    prompt: str

    # Task files
    initial_files: dict[str, str] = field(default_factory=dict)  # path -> content
    test_file: str = ""  # Test file content
    hidden_test_file: str = ""  # Hidden tests for evaluation

    # Expected outcomes
    expected_files: list[str] = field(default_factory=list)

    # Metadata
    tags: list[str] = field(default_factory=list)
    difficulty: str = "medium"  # easy, medium, hard

    # SWE-bench specific (optional)
    swe_metadata: SWEMetadata | None = None

    @property
    def difficulty_score(self) -> int:
        """Get numeric difficulty score for sorting.

        For SWE tasks: uses SWEMetadata.difficulty_score
        For other tasks: maps difficulty string to score (easy=10, medium=50, hard=100)
        """
        if self.swe_metadata and self.swe_metadata.difficulty_score:
            return self.swe_metadata.difficulty_score
        # Fallback for non-SWE tasks
        difficulty_map = {"easy": 10, "medium": 50, "hard": 100}
        return difficulty_map.get(self.difficulty, 50)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tier": self.tier.value,
            "prompt": self.prompt,
            "initial_files": self.initial_files,
            "test_file": self.test_file,
            "hidden_test_file": self.hidden_test_file,
            "expected_files": self.expected_files,
            "tags": self.tags,
            "difficulty": self.difficulty,
        }
        if self.swe_metadata:
            result["swe_metadata"] = self.swe_metadata.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        """Create from dictionary."""
        swe_metadata = None
        if "swe_metadata" in data:
            swe_metadata = SWEMetadata.from_dict(data["swe_metadata"])

        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            tier=TaskTier(data["tier"]),
            prompt=data["prompt"],
            initial_files=data.get("initial_files", {}),
            test_file=data.get("test_file", ""),
            hidden_test_file=data.get("hidden_test_file", ""),
            expected_files=data.get("expected_files", []),
            tags=data.get("tags", []),
            difficulty=data.get("difficulty", "medium"),
            swe_metadata=swe_metadata,
        )


@dataclass
class TaskMetrics:
    """Metrics collected during task execution."""
    # Execution metrics
    iterations: int = 0
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    execution_time_seconds: float = 0.0

    # Cache tokens (from Claude JSONL logs)
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    # Quality metrics
    tests_passed: int = 0
    tests_failed: int = 0
    tests_total: int = 0
    hidden_tests_passed: int = 0
    hidden_tests_total: int = 0

    # Invar-specific metrics (Treatment group only)
    guard_errors: int = 0
    guard_warnings: int = 0
    contract_coverage: float = 0.0
    has_contracts: bool = False

    # Code quality
    lines_of_code: int = 0
    cyclomatic_complexity: float = 0.0

    # Tool usage (from Claude JSONL logs)
    total_tool_calls: int = 0
    mcp_calls: int = 0
    skill_calls: int = 0
    tool_breakdown: dict[str, int] = field(default_factory=dict)

    # Invar protocol adherence
    has_checkin: bool = False
    has_final: bool = False
    final_status: str = ""  # "PASS" or "FAIL"

    # Conversation stats
    assistant_messages: int = 0
    user_messages: int = 0

    @property
    def test_pass_rate(self) -> float:
        """Calculate test pass rate."""
        if self.tests_total == 0:
            return 0.0
        return self.tests_passed / self.tests_total

    @property
    def hidden_test_pass_rate(self) -> float:
        """Calculate hidden test pass rate."""
        if self.hidden_tests_total == 0:
            return 0.0
        return self.hidden_tests_passed / self.hidden_tests_total


@dataclass
class ConversationMessage:
    """A single message in a conversation."""
    role: str  # "user", "assistant", "tool_use", "tool_result"
    content: str
    tool_name: str = ""  # For tool_use/tool_result messages
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = {"role": self.role, "content": self.content}
        if self.tool_name:
            result["tool_name"] = self.tool_name
        if self.timestamp:
            result["timestamp"] = self.timestamp
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationMessage":
        return cls(
            role=data.get("role", ""),
            content=data.get("content", ""),
            tool_name=data.get("tool_name", ""),
            timestamp=data.get("timestamp", ""),
        )


@dataclass
class TaskResult:
    """Result of a single task execution."""
    task_id: str
    group: ExperimentGroup
    status: TaskStatus

    # Execution details
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None

    # Generated files
    generated_files: dict[str, str] = field(default_factory=dict)

    # Metrics
    metrics: TaskMetrics = field(default_factory=TaskMetrics)

    # Logs - structured conversation
    conversation_messages: list[ConversationMessage] = field(default_factory=list)
    conversation_log: str = ""  # Raw output (kept for backwards compatibility)
    error_message: str = ""

    # Conversation statistics (from Claude JSON output)
    total_turns: int = 0
    api_input_tokens: int = 0
    api_output_tokens: int = 0
    api_total_cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "group": self.group.value,
            "status": self.status.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "generated_files": self.generated_files,
            "metrics": {
                "iterations": self.metrics.iterations,
                "total_tokens": self.metrics.total_tokens,
                "input_tokens": self.metrics.input_tokens,
                "output_tokens": self.metrics.output_tokens,
                "execution_time_seconds": self.metrics.execution_time_seconds,
                "cache_creation_tokens": self.metrics.cache_creation_tokens,
                "cache_read_tokens": self.metrics.cache_read_tokens,
                "tests_passed": self.metrics.tests_passed,
                "tests_failed": self.metrics.tests_failed,
                "tests_total": self.metrics.tests_total,
                "hidden_tests_passed": self.metrics.hidden_tests_passed,
                "hidden_tests_total": self.metrics.hidden_tests_total,
                "guard_errors": self.metrics.guard_errors,
                "guard_warnings": self.metrics.guard_warnings,
                "contract_coverage": self.metrics.contract_coverage,
                "has_contracts": self.metrics.has_contracts,
                "lines_of_code": self.metrics.lines_of_code,
                "cyclomatic_complexity": self.metrics.cyclomatic_complexity,
                # Tool usage from Claude JSONL logs
                "total_tool_calls": self.metrics.total_tool_calls,
                "mcp_calls": self.metrics.mcp_calls,
                "skill_calls": self.metrics.skill_calls,
                "tool_breakdown": self.metrics.tool_breakdown,
                # Invar protocol adherence
                "has_checkin": self.metrics.has_checkin,
                "has_final": self.metrics.has_final,
                "final_status": self.metrics.final_status,
                # Conversation stats
                "assistant_messages": self.metrics.assistant_messages,
                "user_messages": self.metrics.user_messages,
            },
            # Structured conversation data
            "conversation": {
                "messages": [m.to_dict() for m in self.conversation_messages],
                "total_turns": self.total_turns,
                "api_input_tokens": self.api_input_tokens,
                "api_output_tokens": self.api_output_tokens,
                "api_total_cost_usd": self.api_total_cost_usd,
            },
            "conversation_log": self.conversation_log,  # Raw output for backwards compatibility
            "error_message": self.error_message,
        }


@dataclass
class ExperimentResult:
    """Aggregated results of an experiment."""
    experiment_id: str
    start_time: datetime
    end_time: datetime | None = None

    # Results by group
    control_results: list[TaskResult] = field(default_factory=list)
    treatment_results: list[TaskResult] = field(default_factory=list)

    # Metadata
    config_snapshot: dict[str, str] = field(default_factory=dict)
    invar_version: str = ""
    claude_code_version: str = ""

    def add_result(self, result: TaskResult) -> None:
        """Add a task result to the appropriate group."""
        if result.group == ExperimentGroup.CONTROL:
            self.control_results.append(result)
        else:
            self.treatment_results.append(result)

    def get_summary(self) -> dict[str, Any]:
        """Get experiment summary statistics."""
        def group_stats(results: list[TaskResult]) -> dict[str, Any]:
            if not results:
                return {}

            completed = [r for r in results if r.status == TaskStatus.COMPLETED]
            return {
                "total_tasks": len(results),
                "completed": len(completed),
                "failed": len([r for r in results if r.status == TaskStatus.FAILED]),
                "timeout": len([r for r in results if r.status == TaskStatus.TIMEOUT]),
                "avg_test_pass_rate": (
                    sum(r.metrics.test_pass_rate for r in completed) / len(completed)
                    if completed else 0.0
                ),
                "avg_hidden_test_pass_rate": (
                    sum(r.metrics.hidden_test_pass_rate for r in completed) / len(completed)
                    if completed else 0.0
                ),
                "avg_iterations": (
                    sum(r.metrics.iterations for r in completed) / len(completed)
                    if completed else 0.0
                ),
                "avg_tokens": (
                    sum(r.metrics.total_tokens for r in completed) / len(completed)
                    if completed else 0.0
                ),
                # New metrics: time, MCP, Skills
                "avg_execution_time": (
                    sum(r.metrics.execution_time_seconds for r in completed) / len(completed)
                    if completed else 0.0
                ),
                "total_execution_time": (
                    sum(r.metrics.execution_time_seconds for r in completed)
                ),
                "avg_mcp_calls": (
                    sum(r.metrics.mcp_calls for r in completed) / len(completed)
                    if completed else 0.0
                ),
                "avg_skill_calls": (
                    sum(r.metrics.skill_calls for r in completed) / len(completed)
                    if completed else 0.0
                ),
                "avg_tool_calls": (
                    sum(r.metrics.total_tool_calls for r in completed) / len(completed)
                    if completed else 0.0
                ),
                # Invar protocol adherence
                "checkin_rate": (
                    sum(1 for r in completed if r.metrics.has_checkin) / len(completed)
                    if completed else 0.0
                ),
                "final_rate": (
                    sum(1 for r in completed if r.metrics.has_final) / len(completed)
                    if completed else 0.0
                ),
                "final_pass_rate": (
                    sum(1 for r in completed if r.metrics.final_status == "PASS") / len(completed)
                    if completed else 0.0
                ),
            }

        return {
            "experiment_id": self.experiment_id,
            "control": group_stats(self.control_results),
            "treatment": group_stats(self.treatment_results),
        }
