"""
Statistical analysis for benchmark results.
"""

import math
from dataclasses import dataclass
from typing import Any


@dataclass
class TTestResult:
    """Result of a t-test."""
    metric_name: str
    control_mean: float
    treatment_mean: float
    control_std: float
    treatment_std: float
    t_statistic: float
    p_value: float
    effect_size: float  # Cohen's d
    significant: bool  # p < 0.05
    warning: str | None = None  # MAJ-2: Statistical warning if any

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "metric_name": self.metric_name,
            "control_mean": self.control_mean,
            "treatment_mean": self.treatment_mean,
            "control_std": self.control_std,
            "treatment_std": self.treatment_std,
            "t_statistic": self.t_statistic,
            "p_value": self.p_value,
            "effect_size": self.effect_size,
            "significant": self.significant,
            "warning": self.warning,
        }


class StatisticalAnalysis:
    """Statistical analysis utilities for benchmark results."""

    @staticmethod
    def mean(values: list[float]) -> float:
        """Calculate mean."""
        if not values:
            return 0.0
        return sum(values) / len(values)

    @staticmethod
    def std(values: list[float]) -> float:
        """Calculate standard deviation."""
        if len(values) < 2:
            return 0.0
        m = StatisticalAnalysis.mean(values)
        variance = sum((x - m) ** 2 for x in values) / (len(values) - 1)
        return math.sqrt(variance)

    @staticmethod
    def cohens_d(
        mean1: float,
        mean2: float,
        std1: float,
        std2: float,
        n1: int,
        n2: int,
    ) -> float:
        """
        Calculate Cohen's d effect size.

        Uses pooled standard deviation.
        """
        if n1 < 2 or n2 < 2:
            return 0.0

        # Pooled standard deviation
        pooled_std = math.sqrt(
            ((n1 - 1) * std1**2 + (n2 - 1) * std2**2) / (n1 + n2 - 2)
        )

        if pooled_std == 0:
            return 0.0

        return (mean2 - mean1) / pooled_std

    @staticmethod
    def welch_t_test(
        values1: list[float],
        values2: list[float],
    ) -> tuple[float, float, str | None]:
        """
        Perform Welch's t-test (unequal variances).

        Returns (t_statistic, p_value, warning_message).
        Uses approximation for p-value without scipy.
        """
        n1 = len(values1)
        n2 = len(values2)

        if n1 < 2 or n2 < 2:
            return 0.0, 1.0, "Insufficient samples (n < 2)"

        mean1 = StatisticalAnalysis.mean(values1)
        mean2 = StatisticalAnalysis.mean(values2)
        var1 = StatisticalAnalysis.std(values1) ** 2
        var2 = StatisticalAnalysis.std(values2) ** 2

        # MAJ-2 fix: Check for zero variance (all values identical)
        warning = None
        if var1 == 0 and var2 == 0:
            warning = "Zero variance in both groups (all values identical)"
            # If means are equal, no difference; otherwise infinite effect
            if mean1 == mean2:
                return 0.0, 1.0, warning
            else:
                # Perfect separation but can't compute t-test
                return float("inf") if mean2 > mean1 else float("-inf"), 0.0, warning

        # Standard error
        se = math.sqrt(var1 / n1 + var2 / n2)

        if se == 0:
            return 0.0, 1.0, "Zero standard error"

        # t-statistic
        t = (mean2 - mean1) / se

        # Welch-Satterthwaite degrees of freedom
        # Avoid division by zero when variance is 0
        df_terms = []
        if var1 > 0:
            df_terms.append((var1 / n1) ** 2 / (n1 - 1))
        if var2 > 0:
            df_terms.append((var2 / n2) ** 2 / (n2 - 1))

        df_num = (var1 / n1 + var2 / n2) ** 2
        df_denom = sum(df_terms) if df_terms else 1
        df = df_num / df_denom if df_denom != 0 else n1 + n2 - 2

        # Approximate p-value using normal distribution for large df
        # For small df, this is an approximation
        p_value = 2 * (1 - StatisticalAnalysis._normal_cdf(abs(t)))

        return t, p_value, warning

    @staticmethod
    def _normal_cdf(x: float) -> float:
        """Approximate standard normal CDF."""
        # Approximation using error function
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def paired_analysis(
        self,
        control_results: list[dict[str, Any]],
        treatment_results: list[dict[str, Any]],
        metric_key: str,
        metric_name: str,
    ) -> TTestResult:
        """
        Perform paired t-test analysis on a metric.

        Args:
            control_results: Control group results
            treatment_results: Treatment group results
            metric_key: Key in metrics dict
            metric_name: Human-readable name

        Returns:
            TTestResult with statistical analysis
        """
        # Extract values
        control_values = [
            r.get("metrics", {}).get(metric_key, 0.0)
            for r in control_results
            if r.get("status") == "completed"
        ]

        treatment_values = [
            r.get("metrics", {}).get(metric_key, 0.0)
            for r in treatment_results
            if r.get("status") == "completed"
        ]

        # Calculate statistics
        control_mean = self.mean(control_values)
        treatment_mean = self.mean(treatment_values)
        control_std = self.std(control_values)
        treatment_std = self.std(treatment_values)

        # Perform t-test (MAJ-2: now returns warning)
        t_stat, p_value, warning = self.welch_t_test(control_values, treatment_values)

        # Calculate effect size
        effect_size = self.cohens_d(
            control_mean, treatment_mean,
            control_std, treatment_std,
            len(control_values), len(treatment_values),
        )

        return TTestResult(
            metric_name=metric_name,
            control_mean=control_mean,
            treatment_mean=treatment_mean,
            control_std=control_std,
            treatment_std=treatment_std,
            t_statistic=t_stat,
            p_value=p_value,
            effect_size=effect_size,
            significant=p_value < 0.05,
            warning=warning,
        )

    def full_analysis(
        self,
        control_results: list[dict[str, Any]],
        treatment_results: list[dict[str, Any]],
    ) -> list[TTestResult]:
        """
        Perform full statistical analysis on all metrics.

        Args:
            control_results: Control group results
            treatment_results: Treatment group results

        Returns:
            List of TTestResult for each metric
        """
        metrics_to_analyze = [
            ("tests_passed", "Tests Passed"),
            ("hidden_tests_passed", "Hidden Tests Passed"),
            ("iterations", "Iterations"),
            ("total_tokens", "Total Tokens"),
            ("lines_of_code", "Lines of Code"),
            ("cyclomatic_complexity", "Cyclomatic Complexity"),
        ]

        results = []
        for key, name in metrics_to_analyze:
            result = self.paired_analysis(
                control_results, treatment_results, key, name
            )
            results.append(result)

        return results

    @staticmethod
    def interpret_effect_size(d: float) -> str:
        """
        Interpret Cohen's d effect size.

        |d| < 0.2: negligible
        0.2 <= |d| < 0.5: small
        0.5 <= |d| < 0.8: medium
        |d| >= 0.8: large
        """
        d = abs(d)
        if d < 0.2:
            return "negligible"
        elif d < 0.5:
            return "small"
        elif d < 0.8:
            return "medium"
        else:
            return "large"
