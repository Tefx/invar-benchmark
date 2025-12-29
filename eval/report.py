"""
Report generation for benchmark results.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from eval.metrics import calculate_metrics, compare_groups, load_results
from eval.analysis import StatisticalAnalysis


def generate_report(results_path: Path, output_path: Path | None = None) -> str:
    """
    Generate a comprehensive report from experiment results.

    Args:
        results_path: Path to results.json
        output_path: Optional path to save report

    Returns:
        Report as markdown string
    """
    # Load results
    results = load_results(results_path)

    # Calculate metrics
    control_metrics = calculate_metrics(
        results.get("control_results", []),
        "Control"
    )
    treatment_metrics = calculate_metrics(
        results.get("treatment_results", []),
        "Treatment"
    )

    # Compare groups
    comparisons = compare_groups(control_metrics, treatment_metrics)

    # Statistical analysis
    analysis = StatisticalAnalysis()
    stats = analysis.full_analysis(
        results.get("control_results", []),
        results.get("treatment_results", []),
    )

    # Generate report
    report = []

    # Header
    report.append("# Invar Benchmark Report")
    report.append("")
    report.append(f"**Experiment ID:** {results.get('experiment_id', 'unknown')}")
    report.append(f"**Generated:** {datetime.now().isoformat()}")
    report.append("")

    # Executive Summary
    report.append("## Executive Summary")
    report.append("")

    # Calculate overall improvement
    test_improvement = (
        treatment_metrics.avg_hidden_test_pass_rate -
        control_metrics.avg_hidden_test_pass_rate
    )
    iteration_reduction = (
        control_metrics.avg_iterations -
        treatment_metrics.avg_iterations
    )

    report.append(f"- **Tasks Completed:** Control {control_metrics.completed_tasks}/{control_metrics.total_tasks}, "
                  f"Treatment {treatment_metrics.completed_tasks}/{treatment_metrics.total_tasks}")
    report.append(f"- **Hidden Test Pass Rate Improvement:** {test_improvement:+.1%}")
    report.append(f"- **Iteration Reduction:** {iteration_reduction:+.1f}")
    report.append(f"- **Contract Usage Rate:** {treatment_metrics.contracts_used_rate:.1%}")
    report.append("")

    # Group Metrics Table
    report.append("## Group Metrics")
    report.append("")
    report.append("| Metric | Control | Treatment | Δ |")
    report.append("|--------|---------|-----------|---|")

    for comp in comparisons:
        icon = "✅" if comp.better_group == "treatment" else ("⚠️" if comp.better_group == "control" else "➖")
        report.append(
            f"| {comp.metric_name} | {comp.control_value:.2f} | "
            f"{comp.treatment_value:.2f} | {icon} {comp.percent_change:+.1f}% |"
        )

    report.append("")

    # Statistical Analysis
    report.append("## Statistical Analysis")
    report.append("")
    report.append("| Metric | Control (μ±σ) | Treatment (μ±σ) | t | p | Effect | Sig? |")
    report.append("|--------|---------------|-----------------|---|---|--------|------|")

    for stat in stats:
        sig_icon = "✓" if stat.significant else "✗"
        effect_interp = analysis.interpret_effect_size(stat.effect_size)
        report.append(
            f"| {stat.metric_name} | "
            f"{stat.control_mean:.2f}±{stat.control_std:.2f} | "
            f"{stat.treatment_mean:.2f}±{stat.treatment_std:.2f} | "
            f"{stat.t_statistic:.2f} | {stat.p_value:.3f} | "
            f"{stat.effect_size:.2f} ({effect_interp}) | {sig_icon} |"
        )

    report.append("")

    # Invar-Specific Metrics (Treatment Only)
    report.append("## Invar-Specific Metrics (Treatment Group)")
    report.append("")
    report.append(f"- **Contract Coverage:** {treatment_metrics.avg_contract_coverage:.1%}")
    report.append(f"- **Contracts Used:** {treatment_metrics.contracts_used_rate:.1%} of tasks")
    report.append(f"- **Avg Guard Errors:** {treatment_metrics.avg_guard_errors:.1f}")
    report.append(f"- **Avg Guard Warnings:** {treatment_metrics.avg_guard_warnings:.1f}")
    report.append("")

    # Conclusions
    report.append("## Conclusions")
    report.append("")

    # Determine overall verdict
    treatment_wins = sum(1 for c in comparisons if c.better_group == "treatment")
    control_wins = sum(1 for c in comparisons if c.better_group == "control")

    if treatment_wins > control_wins:
        report.append("**Verdict:** Treatment group (with Invar) performed better overall.")
    elif control_wins > treatment_wins:
        report.append("**Verdict:** Control group (without Invar) performed better overall.")
    else:
        report.append("**Verdict:** Results are inconclusive - no clear winner.")

    report.append("")

    # Significant findings
    significant_findings = [s for s in stats if s.significant]
    if significant_findings:
        report.append("### Statistically Significant Findings")
        report.append("")
        for finding in significant_findings:
            direction = "higher" if finding.treatment_mean > finding.control_mean else "lower"
            report.append(
                f"- **{finding.metric_name}:** Treatment had significantly {direction} values "
                f"(p={finding.p_value:.3f}, d={finding.effect_size:.2f})"
            )
        report.append("")

    # Recommendations
    report.append("## Recommendations")
    report.append("")
    report.append("Based on the results:")
    report.append("")

    if treatment_metrics.avg_hidden_test_pass_rate > control_metrics.avg_hidden_test_pass_rate:
        report.append("1. **Code Correctness:** Invar improves code correctness as measured by hidden tests.")

    if treatment_metrics.avg_iterations < control_metrics.avg_iterations:
        report.append("2. **Efficiency:** Invar reduces the number of iterations needed to complete tasks.")

    if treatment_metrics.contracts_used_rate > 0.5:
        report.append("3. **Contract Adoption:** High contract usage rate indicates good framework integration.")

    report.append("")
    report.append("---")
    report.append("")
    report.append("*Report generated by Invar Benchmark Framework*")

    # Join and save
    report_text = "\n".join(report)

    if output_path:
        output_path.write_text(report_text)
        print(f"Report saved to: {output_path}")

    return report_text


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Generate benchmark report")

    parser.add_argument(
        "results",
        type=Path,
        help="Path to results.json or experiment directory",
    )

    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output file path (default: stdout)",
    )

    args = parser.parse_args()

    # Resolve results path
    results_path = args.results
    if results_path.is_dir():
        results_path = results_path / "results.json"

    if not results_path.exists():
        print(f"Error: Results file not found: {results_path}")
        return 1

    # Generate report
    report = generate_report(
        results_path,
        args.output,
    )

    if not args.output:
        print(report)

    return 0


if __name__ == "__main__":
    exit(main())
