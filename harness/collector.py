"""
Metrics collection for benchmark tasks.
"""

import ast
import re
import subprocess
from pathlib import Path

from harness.models import ExperimentGroup, Task, TaskMetrics, TaskTier

# Token counting with tiktoken
_tiktoken_encoder = None
_tiktoken_available = False


def _get_tiktoken_encoder():
    """Get or initialize tiktoken encoder (lazy loading)."""
    global _tiktoken_encoder, _tiktoken_available

    if _tiktoken_encoder is not None:
        return _tiktoken_encoder

    try:
        import tiktoken

        # Use cl100k_base encoding (used by Claude, GPT-4, etc.)
        _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
        _tiktoken_available = True
    except Exception:
        _tiktoken_available = False
        _tiktoken_encoder = None

    return _tiktoken_encoder


def count_tokens(text: str) -> tuple[int, bool]:
    """
    Count tokens in text using tiktoken.

    Args:
        text: Text to count tokens for

    Returns:
        Tuple of (token_count, is_accurate)
        - token_count: Number of tokens
        - is_accurate: True if tiktoken was used, False if fallback estimation
    """
    encoder = _get_tiktoken_encoder()

    if encoder is not None:
        try:
            tokens = encoder.encode(text)
            return len(tokens), True
        except Exception:
            pass

    # Fallback: character-based estimation (chars / 4)
    return len(text) // 4, False


class MetricsCollector:
    """Collects metrics from task execution."""

    def collect(
        self,
        workspace: Path,
        task: Task,
        group: ExperimentGroup,
        conversation_log: str,
        repo_dir: Path | None = None,
        use_docker: bool = False,
        docker_timeout: int = 1800,
    ) -> TaskMetrics:
        """
        Collect all metrics for a completed task.

        Args:
            workspace: Task workspace directory
            task: Task definition
            group: Experiment group
            conversation_log: Claude conversation log
            repo_dir: Repository directory for SWE tasks (optional)
            use_docker: Use Docker for SWE evaluation (BM-03 Phase 2)
            docker_timeout: Timeout for Docker evaluation

        Returns:
            TaskMetrics with all collected metrics
        """
        metrics = TaskMetrics()

        # Parse conversation metrics
        self._parse_conversation_metrics(conversation_log, metrics)

        # Check if this is a SWE task
        is_swe_task = task.tier == TaskTier.TIER4_SWE and task.swe_metadata is not None

        if is_swe_task and repo_dir:
            if use_docker:
                # Use Docker-based evaluation (BM-03 Phase 2)
                self._run_docker_evaluation(workspace, task, metrics, docker_timeout)
            else:
                # Run SWE-specific tests directly
                self._run_swe_tests(repo_dir, task, metrics)
        else:
            # Run standard tests
            self._run_tests(workspace, task, metrics)
            self._run_hidden_tests(workspace, task, metrics)

        # Collect code metrics from appropriate directory
        code_dir = repo_dir if (is_swe_task and repo_dir) else workspace
        self._collect_code_metrics(code_dir, metrics)

        # Collect Invar-specific metrics for treatment group
        if group == ExperimentGroup.TREATMENT:
            self._collect_invar_metrics(code_dir, metrics)

        return metrics

    def _parse_conversation_metrics(
        self,
        conversation_log: str,
        metrics: TaskMetrics,
    ) -> None:
        """
        Parse metrics from conversation log.

        Note: If metrics already have token counts (from JSON parsing in runner),
        those values are preserved. This method only estimates if values are 0.
        """
        # Only estimate if not already set by JSON parser
        if metrics.total_tokens == 0:
            # Count iterations (tool calls or message exchanges)
            # This is a simplified heuristic
            tool_calls = conversation_log.count("Tool:") + conversation_log.count("⏺")
            metrics.iterations = max(1, tool_calls)

            # Token counting using tiktoken (improved from MAJ-4)
            # Uses cl100k_base encoding for accurate token counts
            # Falls back to chars/4 estimation if tiktoken unavailable
            token_count, is_accurate = count_tokens(conversation_log)
            metrics.total_tokens = token_count
            metrics.output_tokens = token_count

            # Store accuracy flag in metrics for transparency
            # (Not persisted, but available during collection)
            metrics._token_count_accurate = is_accurate
        else:
            # Token counts already set by JSON parser - mark as accurate
            metrics._token_count_accurate = True

    def _run_tests(
        self,
        workspace: Path,
        task: Task,
        metrics: TaskMetrics,
    ) -> None:
        """Run task tests and collect results."""
        test_file = workspace / "tests" / "test_task.py"

        if not test_file.exists():
            return

        try:
            result = subprocess.run(
                ["python", "-m", "pytest", str(test_file), "-v", "--tb=no"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Parse pytest output
            output = result.stdout + result.stderr

            # Count passed/failed
            passed_match = re.search(r"(\d+) passed", output)
            failed_match = re.search(r"(\d+) failed", output)

            metrics.tests_passed = int(passed_match.group(1)) if passed_match else 0
            metrics.tests_failed = int(failed_match.group(1)) if failed_match else 0
            metrics.tests_total = metrics.tests_passed + metrics.tests_failed

        except Exception:
            pass

    def _run_hidden_tests(
        self,
        workspace: Path,
        task: Task,
        metrics: TaskMetrics,
    ) -> None:
        """Run hidden tests for evaluation."""
        if not task.hidden_test_file:
            return

        # Write hidden tests temporarily
        hidden_test_path = workspace / "tests" / "test_hidden.py"

        try:
            hidden_test_path.write_text(task.hidden_test_file)

            result = subprocess.run(
                ["python", "-m", "pytest", str(hidden_test_path), "-v", "--tb=no"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=60,
            )

            output = result.stdout + result.stderr

            passed_match = re.search(r"(\d+) passed", output)
            failed_match = re.search(r"(\d+) failed", output)

            metrics.hidden_tests_passed = int(passed_match.group(1)) if passed_match else 0
            hidden_failed = int(failed_match.group(1)) if failed_match else 0
            metrics.hidden_tests_total = metrics.hidden_tests_passed + hidden_failed

        except Exception:
            pass

        finally:
            # Clean up
            if hidden_test_path.exists():
                hidden_test_path.unlink()

    def _run_swe_tests(
        self,
        repo_dir: Path,
        task: Task,
        metrics: TaskMetrics,
    ) -> None:
        """
        Run SWE-bench specific tests.

        SWE-bench tasks have:
        - fail_to_pass: Tests that should pass after fix
        - pass_to_pass: Tests that should continue to pass

        Args:
            repo_dir: Path to cloned repository
            task: Task with SWE metadata
            metrics: Metrics to update
        """
        if not task.swe_metadata:
            return

        fail_to_pass = task.swe_metadata.fail_to_pass
        pass_to_pass = task.swe_metadata.pass_to_pass

        # Run fail_to_pass tests (these are the "hidden" tests - must pass after fix)
        if fail_to_pass:
            passed = 0
            failed = 0

            for test_spec in fail_to_pass:
                try:
                    result = subprocess.run(
                        ["python", "-m", "pytest", test_spec, "-v", "--tb=no"],
                        cwd=repo_dir,
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )

                    if result.returncode == 0:
                        passed += 1
                    else:
                        failed += 1

                except Exception:
                    failed += 1

            # fail_to_pass are treated as hidden tests
            metrics.hidden_tests_passed = passed
            metrics.hidden_tests_total = passed + failed

        # Run pass_to_pass tests (regression tests - must continue to pass)
        if pass_to_pass:
            passed = 0
            failed = 0

            for test_spec in pass_to_pass:
                try:
                    result = subprocess.run(
                        ["python", "-m", "pytest", test_spec, "-v", "--tb=no"],
                        cwd=repo_dir,
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )

                    if result.returncode == 0:
                        passed += 1
                    else:
                        failed += 1

                except Exception:
                    failed += 1

            # pass_to_pass are treated as regular tests
            metrics.tests_passed = passed
            metrics.tests_failed = failed
            metrics.tests_total = passed + failed

    def _run_docker_evaluation(
        self,
        workspace: Path,
        task: Task,
        metrics: TaskMetrics,
        timeout: int = 1800,
    ) -> None:
        """
        Run Docker-based SWE-bench evaluation.

        Uses swebench's Docker harness for isolated, reproducible evaluation.

        Args:
            workspace: Task workspace directory
            task: Task with SWE metadata
            metrics: Metrics to update
            timeout: Timeout for Docker evaluation
        """
        try:
            from harness.docker_runner import run_swe_task_with_docker

            result = run_swe_task_with_docker(
                task=task,
                workspace=workspace,
                timeout=timeout,
            )

            if result.get("docker_eval"):
                # Docker evaluation ran
                if result.get("resolved"):
                    # Task was resolved - all fail_to_pass tests passed
                    fail_to_pass_count = len(task.swe_metadata.fail_to_pass) if task.swe_metadata else 0
                    metrics.hidden_tests_passed = fail_to_pass_count
                    metrics.hidden_tests_total = fail_to_pass_count
                else:
                    # Task not resolved
                    metrics.hidden_tests_passed = result.get("tests_passed", 0)
                    metrics.hidden_tests_total = (
                        result.get("tests_passed", 0) + result.get("tests_failed", 0)
                    )

                # Pass-to-pass tests (if available)
                metrics.tests_passed = result.get("tests_passed", 0)
                metrics.tests_total = result.get("tests_passed", 0) + result.get("tests_failed", 0)

        except ImportError:
            # Docker runner not available, fall back to direct tests
            pass
        except Exception:
            # Docker evaluation failed, metrics remain at defaults
            pass

    def _collect_code_metrics(
        self,
        workspace: Path,
        metrics: TaskMetrics,
    ) -> None:
        """Collect code quality metrics."""
        total_lines = 0

        for py_file in workspace.rglob("*.py"):
            if "__pycache__" in str(py_file) or py_file.name.startswith("."):
                continue

            if "test" in py_file.name.lower():
                continue

            try:
                content = py_file.read_text()
                # Count non-empty, non-comment lines
                for line in content.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        total_lines += 1
            except Exception:
                pass

        metrics.lines_of_code = total_lines

        # Simple cyclomatic complexity estimate
        # (Count decision points: if, for, while, except, and, or)
        try:
            complexity = 0
            for py_file in workspace.rglob("*.py"):
                if "__pycache__" in str(py_file):
                    continue
                if "test" in py_file.name.lower():
                    continue

                content = py_file.read_text()
                complexity += len(re.findall(r"\b(if|for|while|except|and|or)\b", content))

            metrics.cyclomatic_complexity = complexity / max(1, total_lines) * 10

        except Exception:
            pass

    def _count_contracts_ast(self, content: str) -> tuple[int, int, bool]:
        """
        Count contracts and functions using AST (MAJ-1 fix).

        Returns:
            (contract_count, function_count, has_contracts)
        """
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return 0, 0, False

        contract_count = 0
        function_count = 0
        has_contracts = False

        # Known contract decorator names
        contract_names = {"pre", "post", "require", "ensure", "invariant"}

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_count += 1

                for decorator in node.decorator_list:
                    decorator_name = None

                    # Handle @pre(...) or @post(...)
                    if isinstance(decorator, ast.Call):
                        if isinstance(decorator.func, ast.Name):
                            decorator_name = decorator.func.id
                        elif isinstance(decorator.func, ast.Attribute):
                            # Handle @deal.pre(...) or @contract.pre(...)
                            decorator_name = decorator.func.attr

                    # Handle @pre (without call, less common)
                    elif isinstance(decorator, ast.Name):
                        decorator_name = decorator.id
                    elif isinstance(decorator, ast.Attribute):
                        decorator_name = decorator.attr

                    if decorator_name and decorator_name.lower() in contract_names:
                        contract_count += 1
                        has_contracts = True

        return contract_count, function_count, has_contracts

    def _collect_invar_metrics(
        self,
        workspace: Path,
        metrics: TaskMetrics,
    ) -> None:
        """Collect Invar-specific metrics for treatment group."""
        total_contracts = 0
        total_functions = 0
        has_any_contracts = False

        for py_file in workspace.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            if "test" in py_file.name.lower():
                continue

            try:
                content = py_file.read_text()
                contracts, functions, has_contracts = self._count_contracts_ast(content)
                total_contracts += contracts
                total_functions += functions
                if has_contracts:
                    has_any_contracts = True
            except Exception:
                pass

        metrics.has_contracts = has_any_contracts
        # Coverage: contracts / (functions * 2) because ideal is pre+post per function
        metrics.contract_coverage = (
            total_contracts / max(1, total_functions * 2)
        )

        # Run invar guard if available
        try:
            result = subprocess.run(
                ["invar", "guard", "--json"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                try:
                    import json
                    guard_output = json.loads(result.stdout)
                    metrics.guard_errors = guard_output.get("errors", 0)
                    metrics.guard_warnings = guard_output.get("warnings", 0)
                except Exception:
                    pass

        except Exception:
            pass
