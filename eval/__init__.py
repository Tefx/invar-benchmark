"""
Invar Benchmark Evaluation

Statistical analysis and reporting for benchmark results.
"""

from eval.metrics import calculate_metrics, compare_groups
from eval.analysis import StatisticalAnalysis
from eval.report import generate_report

__all__ = [
    "calculate_metrics",
    "compare_groups",
    "StatisticalAnalysis",
    "generate_report",
]
