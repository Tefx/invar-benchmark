"""
Docker-based SWE-bench evaluation runner.

Uses swebench's Docker harness for reproducible, isolated test execution.
"""

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.models import Task, SWEMetadata


@dataclass
class DockerEvalResult:
    """Result from Docker-based SWE evaluation."""

    instance_id: str
    resolved: bool
    tests_passed: int
    tests_failed: int
    error_message: str = ""


def check_docker_available() -> tuple[bool, str]:
    """
    Check if Docker is available and running.

    Returns:
        Tuple of (available, message)
    """
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return True, "Docker is available"
        return False, f"Docker not running: {result.stderr}"
    except FileNotFoundError:
        return False, "Docker not installed"
    except subprocess.TimeoutExpired:
        return False, "Docker check timed out"


def check_swebench_available() -> tuple[bool, str]:
    """
    Check if swebench package is installed.

    Returns:
        Tuple of (available, message)
    """
    try:
        import swebench  # noqa: F401

        return True, "swebench is available"
    except ImportError:
        return False, "swebench not installed. Run: pip install swebench"


def extract_patch_from_workspace(workspace: Path, base_commit: str = "") -> str:
    """
    Extract git diff from workspace after Claude's modifications.

    Args:
        workspace: Path to workspace with repo subdirectory
        base_commit: Base commit to diff against (optional)

    Returns:
        Unified diff string
    """
    repo_dir = workspace / "repo"
    if not repo_dir.exists():
        return ""

    try:
        # Get diff of all changes
        cmd = ["git", "diff"]
        if base_commit:
            cmd.append(base_commit)

        result = subprocess.run(
            cmd,
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            return result.stdout

        return ""
    except Exception:
        return ""


def create_predictions_file(
    instance_id: str,
    model_patch: str,
    model_name: str = "invar-benchmark",
    output_path: Path | None = None,
) -> Path:
    """
    Create a predictions JSONL file for swebench evaluation.

    Args:
        instance_id: SWE-bench instance ID (e.g., "astropy__astropy-14539")
        model_patch: Unified diff patch string
        model_name: Model identifier
        output_path: Optional output path (creates temp file if None)

    Returns:
        Path to the predictions file
    """
    prediction = {
        "instance_id": instance_id,
        "model_name_or_path": model_name,
        "model_patch": model_patch,
    }

    if output_path is None:
        # Create temporary file
        fd, path = tempfile.mkstemp(suffix=".jsonl", prefix="swe_pred_")
        output_path = Path(path)

    with open(output_path, "w") as f:
        f.write(json.dumps(prediction) + "\n")

    return output_path


def run_docker_evaluation(
    task: Task,
    model_patch: str,
    timeout: int = 1800,
    max_workers: int = 1,
    run_id: str = "invar-eval",
) -> DockerEvalResult:
    """
    Run SWE-bench evaluation in Docker container.

    Args:
        task: Task with SWE metadata
        model_patch: Unified diff patch to evaluate
        timeout: Timeout per instance in seconds
        max_workers: Number of parallel workers
        run_id: Identifier for this evaluation run

    Returns:
        DockerEvalResult with evaluation results
    """
    if not task.swe_metadata:
        return DockerEvalResult(
            instance_id="",
            resolved=False,
            tests_passed=0,
            tests_failed=0,
            error_message="Task has no SWE metadata",
        )

    instance_id = task.swe_metadata.instance_id

    # Check prerequisites
    docker_ok, docker_msg = check_docker_available()
    if not docker_ok:
        return DockerEvalResult(
            instance_id=instance_id,
            resolved=False,
            tests_passed=0,
            tests_failed=0,
            error_message=docker_msg,
        )

    swe_ok, swe_msg = check_swebench_available()
    if not swe_ok:
        return DockerEvalResult(
            instance_id=instance_id,
            resolved=False,
            tests_passed=0,
            tests_failed=0,
            error_message=swe_msg,
        )

    # Create predictions file
    predictions_path = create_predictions_file(
        instance_id=instance_id,
        model_patch=model_patch,
        model_name="invar-benchmark",
    )

    try:
        # Import swebench here to avoid import error when not installed
        from swebench.harness.run_evaluation import main as swebench_main

        # Run evaluation
        swebench_main(
            dataset_name="princeton-nlp/SWE-bench_Lite",
            split="test",
            instance_ids=[instance_id],
            predictions_path=str(predictions_path),
            max_workers=max_workers,
            force_rebuild=False,
            cache_level="env",
            clean=False,
            open_file_limit=4096,
            run_id=run_id,
            timeout=timeout,
            namespace=None,  # Build locally on ARM Macs
            rewrite_reports=False,
            modal=False,
        )

        # Parse results
        return _parse_evaluation_results(instance_id, run_id)

    except Exception as e:
        return DockerEvalResult(
            instance_id=instance_id,
            resolved=False,
            tests_passed=0,
            tests_failed=0,
            error_message=str(e),
        )
    finally:
        # Cleanup predictions file
        if predictions_path.exists():
            predictions_path.unlink()


def _parse_evaluation_results(
    instance_id: str,
    run_id: str,
    model_name: str = "invar-benchmark",
) -> DockerEvalResult:
    """
    Parse swebench evaluation results from output files.

    Args:
        instance_id: Instance that was evaluated
        run_id: Run identifier to find result files
        model_name: Model name used in predictions

    Returns:
        DockerEvalResult parsed from output
    """
    # swebench writes results to logs/run_evaluation/{run_id}/{model_name}/{instance_id}/
    result_dir = Path(f"logs/run_evaluation/{run_id}/{model_name}/{instance_id}")

    # Look for report file (swebench structure)
    report_file = result_dir / "report.json"

    if report_file.exists():
        try:
            with open(report_file) as f:
                report = json.load(f)

            # Report is keyed by instance_id
            instance_report = report.get(instance_id, {})
            resolved = instance_report.get("resolved", False)

            # Count tests from tests_status
            tests_status = instance_report.get("tests_status", {})
            fail_to_pass = tests_status.get("FAIL_TO_PASS", {})
            pass_to_pass = tests_status.get("PASS_TO_PASS", {})

            # Tests passed = success count from FAIL_TO_PASS + PASS_TO_PASS
            tests_passed = len(fail_to_pass.get("success", []))
            tests_failed = len(fail_to_pass.get("failure", []))

            # For hidden tests (fail_to_pass)
            hidden_passed = len(fail_to_pass.get("success", []))
            hidden_total = hidden_passed + len(fail_to_pass.get("failure", []))

            return DockerEvalResult(
                instance_id=instance_id,
                resolved=resolved,
                tests_passed=hidden_passed,
                tests_failed=tests_failed,
            )
        except Exception:
            pass

    # Fallback: check old-style result path
    old_result_dir = Path(f"logs/run_evaluation/{run_id}")
    old_report_file = old_result_dir / f"{instance_id}.json"
    if old_report_file.exists():
        try:
            with open(old_report_file) as f:
                report = json.load(f)

            return DockerEvalResult(
                instance_id=instance_id,
                resolved=report.get("resolved", False),
                tests_passed=report.get("tests_passed", 0),
                tests_failed=report.get("tests_failed", 0),
            )
        except Exception:
            pass

    # Fallback: check summary file
    summary_file = old_result_dir / "results.json"
    if summary_file.exists():
        try:
            with open(summary_file) as f:
                summary = json.load(f)

            resolved = instance_id in summary.get("resolved", [])
            return DockerEvalResult(
                instance_id=instance_id,
                resolved=resolved,
                tests_passed=1 if resolved else 0,
                tests_failed=0 if resolved else 1,
            )
        except Exception:
            pass

    return DockerEvalResult(
        instance_id=instance_id,
        resolved=False,
        tests_passed=0,
        tests_failed=0,
        error_message="Could not parse evaluation results",
    )


def run_swe_task_with_docker(
    task: Task,
    workspace: Path,
    timeout: int = 1800,
) -> dict[str, Any]:
    """
    High-level function to evaluate a SWE task using Docker.

    This extracts the patch from the workspace and runs swebench evaluation.

    Args:
        task: Task with SWE metadata
        workspace: Workspace where Claude made changes
        timeout: Evaluation timeout

    Returns:
        Dictionary with evaluation results for metrics collection
    """
    if not task.swe_metadata:
        return {
            "docker_eval": False,
            "error": "No SWE metadata",
        }

    # Extract patch from workspace
    base_commit = task.swe_metadata.base_commit
    model_patch = extract_patch_from_workspace(workspace, base_commit)

    if not model_patch:
        return {
            "docker_eval": True,
            "resolved": False,
            "tests_passed": 0,
            "tests_failed": len(task.swe_metadata.fail_to_pass),
            "error": "No changes detected in workspace",
        }

    # Run Docker evaluation
    result = run_docker_evaluation(
        task=task,
        model_patch=model_patch,
        timeout=timeout,
    )

    return {
        "docker_eval": True,
        "resolved": result.resolved,
        "tests_passed": result.tests_passed,
        "tests_failed": result.tests_failed,
        "error": result.error_message if result.error_message else None,
    }
