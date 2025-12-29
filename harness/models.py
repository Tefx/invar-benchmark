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
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SWEMetadata":
        return cls(
            instance_id=data.get("instance_id", ""),
            repo=data.get("repo", ""),
            base_commit=data.get("base_commit", ""),
            test_patch=data.get("test_patch", ""),
            gold_patch=data.get("gold_patch", ""),
            fail_to_pass=data.get("fail_to_pass", []),
            pass_to_pass=data.get("pass_to_pass", []),
            version=data.get("version", ""),
            environment_setup_commit=data.get("environment_setup_commit", ""),
        )


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

    # Logs
    conversation_log: str = ""
    error_message: str = ""

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
            },
            "conversation_log": self.conversation_log,
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
            }

        return {
            "experiment_id": self.experiment_id,
            "control": group_stats(self.control_results),
            "treatment": group_stats(self.treatment_results),
        }
