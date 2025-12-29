"""
Metrics calculation for benchmark evaluation.
"""

from dataclasses import dataclass
from typing import Any

import json
from pathlib import Path


@dataclass
class GroupMetrics:
    """Aggregated metrics for an experiment group."""
    group_name: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    timeout_tasks: int

    # Test metrics
    avg_test_pass_rate: float
    avg_hidden_test_pass_rate: float

    # Efficiency metrics
    avg_iterations: float
    avg_tokens: float
    avg_execution_time: float

    # Code quality metrics
    avg_lines_of_code: float
    avg_complexity: float

    # Invar-specific (treatment only)
    avg_contract_coverage: float
    contracts_used_rate: float
    avg_guard_errors: float
    avg_guard_warnings: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "group_name": self.group_name,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "timeout_tasks": self.timeout_tasks,
            "avg_test_pass_rate": self.avg_test_pass_rate,
            "avg_hidden_test_pass_rate": self.avg_hidden_test_pass_rate,
            "avg_iterations": self.avg_iterations,
            "avg_tokens": self.avg_tokens,
            "avg_execution_time": self.avg_execution_time,
            "avg_lines_of_code": self.avg_lines_of_code,
            "avg_complexity": self.avg_complexity,
            "avg_contract_coverage": self.avg_contract_coverage,
            "contracts_used_rate": self.contracts_used_rate,
            "avg_guard_errors": self.avg_guard_errors,
            "avg_guard_warnings": self.avg_guard_warnings,
        }


def calculate_metrics(results: list[dict[str, Any]], group_name: str) -> GroupMetrics:
    """
    Calculate aggregated metrics for a group of results.

    Args:
        results: List of task result dictionaries
        group_name: Name of the group

    Returns:
        GroupMetrics with aggregated statistics
    """
    if not results:
        return GroupMetrics(
            group_name=group_name,
            total_tasks=0,
            completed_tasks=0,
            failed_tasks=0,
            timeout_tasks=0,
            avg_test_pass_rate=0.0,
            avg_hidden_test_pass_rate=0.0,
            avg_iterations=0.0,
            avg_tokens=0.0,
            avg_execution_time=0.0,
            avg_lines_of_code=0.0,
            avg_complexity=0.0,
            avg_contract_coverage=0.0,
            contracts_used_rate=0.0,
            avg_guard_errors=0.0,
            avg_guard_warnings=0.0,
        )

    # Count by status
    completed = [r for r in results if r.get("status") == "completed"]
    failed = [r for r in results if r.get("status") == "failed"]
    timeout = [r for r in results if r.get("status") == "timeout"]

    # Calculate averages from completed tasks
    def avg(key: str, default: float = 0.0) -> float:
        if not completed:
            return default
        values = [r.get("metrics", {}).get(key, default) for r in completed]
        return sum(values) / len(values)

    # Test pass rates
    def test_pass_rate(r: dict) -> float:
        metrics = r.get("metrics", {})
        total = metrics.get("tests_total", 0)
        passed = metrics.get("tests_passed", 0)
        return passed / total if total > 0 else 0.0

    def hidden_pass_rate(r: dict) -> float:
        metrics = r.get("metrics", {})
        total = metrics.get("hidden_tests_total", 0)
        passed = metrics.get("hidden_tests_passed", 0)
        return passed / total if total > 0 else 0.0

    avg_test_rate = (
        sum(test_pass_rate(r) for r in completed) / len(completed)
        if completed else 0.0
    )

    avg_hidden_rate = (
        sum(hidden_pass_rate(r) for r in completed) / len(completed)
        if completed else 0.0
    )

    # Contract usage rate
    contracts_used = sum(
        1 for r in completed
        if r.get("metrics", {}).get("has_contracts", False)
    )
    contracts_rate = contracts_used / len(completed) if completed else 0.0

    return GroupMetrics(
        group_name=group_name,
        total_tasks=len(results),
        completed_tasks=len(completed),
        failed_tasks=len(failed),
        timeout_tasks=len(timeout),
        avg_test_pass_rate=avg_test_rate,
        avg_hidden_test_pass_rate=avg_hidden_rate,
        avg_iterations=avg("iterations"),
        avg_tokens=avg("total_tokens"),
        avg_execution_time=avg("execution_time_seconds"),
        avg_lines_of_code=avg("lines_of_code"),
        avg_complexity=avg("cyclomatic_complexity"),
        avg_contract_coverage=avg("contract_coverage"),
        contracts_used_rate=contracts_rate,
        avg_guard_errors=avg("guard_errors"),
        avg_guard_warnings=avg("guard_warnings"),
    )


@dataclass
class GroupComparison:
    """Comparison between control and treatment groups."""
    metric_name: str
    control_value: float
    treatment_value: float
    difference: float
    percent_change: float
    better_group: str  # 'control', 'treatment', or 'tie'

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "metric_name": self.metric_name,
            "control_value": self.control_value,
            "treatment_value": self.treatment_value,
            "difference": self.difference,
            "percent_change": self.percent_change,
            "better_group": self.better_group,
        }


def compare_groups(
    control: GroupMetrics,
    treatment: GroupMetrics,
) -> list[GroupComparison]:
    """
    Compare metrics between control and treatment groups.

    Args:
        control: Control group metrics
        treatment: Treatment group metrics

    Returns:
        List of comparisons for each metric
    """
    comparisons = []

    # Define metrics to compare and whether higher is better
    metrics_config = [
        ("avg_test_pass_rate", True, "Test Pass Rate"),
        ("avg_hidden_test_pass_rate", True, "Hidden Test Pass Rate"),
        ("avg_iterations", False, "Iterations (lower is better)"),
        ("avg_tokens", False, "Token Usage (lower is better)"),
        ("avg_lines_of_code", False, "Lines of Code"),
        ("avg_complexity", False, "Complexity (lower is better)"),
    ]

    for attr, higher_is_better, display_name in metrics_config:
        control_val = getattr(control, attr)
        treatment_val = getattr(treatment, attr)

        diff = treatment_val - control_val
        pct_change = (
            (diff / control_val * 100) if control_val != 0 else 0.0
        )

        if higher_is_better:
            better = "treatment" if diff > 0 else ("control" if diff < 0 else "tie")
        else:
            better = "treatment" if diff < 0 else ("control" if diff > 0 else "tie")

        comparisons.append(GroupComparison(
            metric_name=display_name,
            control_value=control_val,
            treatment_value=treatment_val,
            difference=diff,
            percent_change=pct_change,
            better_group=better,
        ))

    return comparisons


def load_results(results_path: Path) -> dict[str, Any]:
    """
    Load results from a results.json file.

    Args:
        results_path: Path to results.json

    Returns:
        Results dictionary
    """
    with open(results_path) as f:
        return json.load(f)
