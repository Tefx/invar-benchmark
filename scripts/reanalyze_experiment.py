#!/usr/bin/env python3
"""
Reanalyze an experiment with accurate metrics from Claude's JSONL logs.

Usage:
    python scripts/reanalyze_experiment.py results/exp_20251229_174928
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.conversation_parser import parse_workspace_conversation


def reanalyze_experiment(results_dir: Path) -> dict:
    """
    Reanalyze an experiment using Claude's JSONL conversation logs.

    Args:
        results_dir: Path to the experiment results directory

    Returns:
        Updated results dictionary with accurate metrics
    """
    results_file = results_dir / "results.json"
    if not results_file.exists():
        print(f"Error: {results_file} not found")
        sys.exit(1)

    with open(results_file) as f:
        data = json.load(f)

    config = data.get("config", {}).get("config", {})
    benchmark_root = Path(config.get("benchmark_root", "."))

    print(f"Reanalyzing experiment: {data['experiment_id']}")
    print(f"Benchmark root: {benchmark_root}")
    print()

    # Process each group
    for group in ["control_results", "treatment_results"]:
        print(f"\n=== {group.upper()} ===")
        results = data.get(group, [])

        for result in results:
            task_id = result["task_id"]
            group_name = result["group"]

            # Construct workspace path
            workspace = benchmark_root / "workspace" / group_name / task_id

            print(f"\n{task_id}:")
            print(f"  Workspace: {workspace}")

            # Parse conversation logs with time filtering
            start_time = result.get("start_time")
            end_time = result.get("end_time")
            conv_metrics = parse_workspace_conversation(workspace, start_time, end_time)

            if conv_metrics is None:
                print("  [No conversation found]")
                continue

            # Update metrics
            old_metrics = result.get("metrics", {})

            print(f"  Old iterations: {old_metrics.get('iterations', 0)} -> {conv_metrics.assistant_messages}")
            print(f"  Old input_tokens: {old_metrics.get('input_tokens', 0)} -> {conv_metrics.input_tokens}")
            print(f"  Old output_tokens: {old_metrics.get('output_tokens', 0)} -> {conv_metrics.output_tokens}")
            print(f"  Old total_tokens: {old_metrics.get('total_tokens', 0)} -> {conv_metrics.total_tokens}")
            print(f"  Tool calls: {conv_metrics.total_tool_calls}")
            print(f"  MCP calls: {conv_metrics.total_mcp_calls}")
            print(f"  Skill calls: {conv_metrics.skill_calls}")
            print(f"  Check-In: {'✓' if conv_metrics.has_checkin else '-'}")
            print(f"  Final: {'✓' if conv_metrics.has_final else '-'} ({conv_metrics.final_status})")

            # Update the result with accurate metrics
            result["metrics"]["iterations"] = conv_metrics.assistant_messages
            result["metrics"]["input_tokens"] = conv_metrics.input_tokens
            result["metrics"]["output_tokens"] = conv_metrics.output_tokens
            result["metrics"]["total_tokens"] = conv_metrics.total_tokens
            result["metrics"]["cache_creation_tokens"] = conv_metrics.cache_creation_tokens
            result["metrics"]["cache_read_tokens"] = conv_metrics.cache_read_tokens
            result["metrics"]["total_tool_calls"] = conv_metrics.total_tool_calls
            result["metrics"]["mcp_calls"] = conv_metrics.total_mcp_calls
            result["metrics"]["skill_calls"] = conv_metrics.skill_calls
            result["metrics"]["has_checkin"] = conv_metrics.has_checkin
            result["metrics"]["has_final"] = conv_metrics.has_final
            result["metrics"]["final_status"] = conv_metrics.final_status
            result["metrics"]["assistant_messages"] = conv_metrics.assistant_messages
            result["metrics"]["user_messages"] = conv_metrics.user_messages
            result["metrics"]["tool_breakdown"] = conv_metrics.tool_uses

    return data


def print_comparison(data: dict) -> None:
    """Print a comparison table of control vs treatment."""
    control = data.get("control_results", [])
    treatment = data.get("treatment_results", [])

    print("\n" + "=" * 80)
    print("COMPARISON: Control vs Treatment (with accurate metrics)")
    print("=" * 80)

    # Header
    print(f"\n{'Metric':<25} {'Control':>20} {'Treatment':>20} {'Delta':>15}")
    print("-" * 80)

    def avg(results, key, nested=False):
        if nested:
            values = [r.get("metrics", {}).get(key, 0) for r in results]
        else:
            values = [r.get(key, 0) for r in results]
        return sum(values) / len(values) if values else 0

    def total(results, key):
        return sum(r.get("metrics", {}).get(key, 0) for r in results)

    def rate(results, key):
        count = sum(1 for r in results if r.get("metrics", {}).get(key, False))
        return count / len(results) if results else 0

    # Metrics
    metrics = [
        ("Completed", len(control), len(treatment), ""),
        ("Avg Iterations", avg(control, "iterations", True), avg(treatment, "iterations", True), "lower=better"),
        ("Avg Tokens", avg(control, "total_tokens", True), avg(treatment, "total_tokens", True), "lower=better"),
        ("Avg Tool Calls", avg(control, "total_tool_calls", True), avg(treatment, "total_tool_calls", True), ""),
        ("Avg MCP Calls", avg(control, "mcp_calls", True), avg(treatment, "mcp_calls", True), "treatment only"),
        ("Avg Skill Calls", avg(control, "skill_calls", True), avg(treatment, "skill_calls", True), "treatment only"),
        ("Avg Exec Time (s)", avg(control, "execution_time_seconds", True), avg(treatment, "execution_time_seconds", True), "lower=better"),
        ("Total Exec Time (s)", total(control, "execution_time_seconds"), total(treatment, "execution_time_seconds"), "lower=better"),
        ("Check-In Rate", rate(control, "has_checkin"), rate(treatment, "has_checkin"), "higher=better"),
        ("Final Rate", rate(control, "has_final"), rate(treatment, "has_final"), "higher=better"),
    ]

    for name, c_val, t_val, note in metrics:
        if isinstance(c_val, float):
            if name.endswith("Rate"):
                c_str = f"{c_val:.0%}"
                t_str = f"{t_val:.0%}"
            else:
                c_str = f"{c_val:.1f}"
                t_str = f"{t_val:.1f}"
        else:
            c_str = str(c_val)
            t_str = str(t_val)

        delta = ""
        if isinstance(c_val, (int, float)) and isinstance(t_val, (int, float)) and c_val > 0:
            pct = ((t_val - c_val) / c_val) * 100
            sign = "+" if pct > 0 else ""
            delta = f"{sign}{pct:.1f}%"

        print(f"{name:<25} {c_str:>20} {t_str:>20} {delta:>15}")

    print()


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/reanalyze_experiment.py <results_dir>")
        print("Example: python scripts/reanalyze_experiment.py results/exp_20251229_174928")
        sys.exit(1)

    results_dir = Path(sys.argv[1])
    if not results_dir.exists():
        print(f"Error: {results_dir} does not exist")
        sys.exit(1)

    # Reanalyze
    data = reanalyze_experiment(results_dir)

    # Print comparison
    print_comparison(data)

    # Save updated results
    output_file = results_dir / "results_reanalyzed.json"
    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved updated results to: {output_file}")


if __name__ == "__main__":
    main()
