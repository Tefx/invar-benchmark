"""
Benchmark task runner.
"""

import argparse
import json
import os
import pty
import select
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from harness.config import (
    BenchmarkConfig,
    create_experiment_metadata,
    setup_workspace,
    setup_swe_workspace,
    get_cache_stats,
    clear_cache,
)
from harness.models import (
    ExperimentGroup,
    ExperimentResult,
    Task,
    TaskResult,
    TaskStatus,
    TaskTier,
)
from harness.collector import MetricsCollector

# ProgressDisplay imported lazily in _run_with_rich_display to avoid rich dependency
# for simple commands like --check-docker

# USBV Skill prefix for treatment group prompts (PRINT MODE)
# Embeds key /develop skill guidance directly in prompt since Skill tool unavailable
USBV_SKILL_PREFIX_PRINT = """# Development Instructions (USBV Workflow)

Follow this workflow:
1. UNDERSTAND: What needs to be done? Check existing code structure.
2. SPECIFY: Write @pre/@post contracts BEFORE implementation.
3. BUILD: Implement following the contracts.
4. VALIDATE: Run invar guard to verify.

Required output:
- Show: ✓ Check-In: [project] | [branch] | [status]
- Show: ✓ Final: guard PASS | errors, warnings

Contract pattern (MUST use):
```python
from deal import pre, post

@pre(lambda x: x > 0)  # Precondition
@post(lambda result: result >= 0)  # Postcondition
def calculate(x: int) -> int:
    '''
    >>> calculate(10)
    100
    '''
    return x * x
```

Core functions go in src/core/ with @pre/@post.
Shell functions go in src/shell/ with Result[T, E] return type.

---
Task:
"""

# Skill trigger prefix for treatment group prompts (INTERACTIVE MODE)
# Uses trigger words to activate routing rules in CLAUDE.md → invokes /develop skill
USBV_SKILL_PREFIX_INTERACTIVE = """Implement the following task using the /develop skill workflow.

Task:
"""


class BenchmarkRunner:
    """Runs benchmark tasks against Claude Code."""

    def __init__(self, config: BenchmarkConfig):
        self.config = config
        self.collector = MetricsCollector()

    def load_tasks(self, tier: str | None = None) -> list[Task]:
        """
        Load tasks from the tasks directory.

        Args:
            tier: Optional tier filter ('tier1_standard' or 'tier2_contracts')

        Returns:
            List of Task objects
        """
        tasks = []

        for task_dir in sorted(self.config.tasks_dir.iterdir()):
            if not task_dir.is_dir():
                continue

            # Filter by tier if specified
            if tier and task_dir.name != tier:
                continue

            for task_file in sorted(task_dir.glob("*.json")):
                with open(task_file) as f:
                    task_data = json.load(f)
                    tasks.append(Task.from_dict(task_data))

        return tasks

    def run_task(
        self,
        task: Task,
        group: ExperimentGroup,
        quiet: bool = False,
    ) -> TaskResult:
        """
        Run a single task for a specific group.

        Args:
            task: Task to run
            group: Experiment group (control or treatment)
            quiet: Suppress warning messages (for Rich display)

        Returns:
            TaskResult with execution details and metrics
        """
        result = TaskResult(
            task_id=task.id,
            group=group,
            status=TaskStatus.RUNNING,
            start_time=datetime.now(),
        )

        try:
            # Setup workspace - use SWE setup for tier4_swe tasks with real repos
            # If initial_files is non-empty, use standard setup (for sample/test tasks)
            is_swe_task = (
                task.tier == TaskTier.TIER4_SWE
                and task.swe_metadata is not None
                and task.swe_metadata.repo
                and not task.initial_files  # Has no local files - needs clone
            )

            if is_swe_task:
                workspace = setup_swe_workspace(
                    self.config,
                    group.value,
                    task.id,
                    task.swe_metadata.to_dict(),
                )
                # For SWE tasks, tests run inside the repo directory
                repo_dir = workspace / "repo"
            else:
                workspace = setup_workspace(
                    self.config,
                    group.value,
                    task.id,
                    task.initial_files,
                )
                repo_dir = workspace

            # Write test file (for non-SWE tasks or hidden tests)
            if task.test_file:
                test_path = workspace / "tests" / "test_task.py"
                test_path.write_text(task.test_file)

            # Build Claude command
            cmd = [self.config.claude_command]

            # Add model selection
            if self.config.claude_model:
                cmd.extend(["--model", self.config.claude_model])

            # Determine execution mode
            use_interactive = self.config.execution_mode == "interactive"

            if use_interactive:
                # Interactive mode: use PTY simulation
                cmd.append("--dangerously-skip-permissions")
                if self.config.max_turns:
                    cmd.extend(["--max-turns", str(self.config.max_turns)])
            else:
                # Print mode: non-interactive single-shot
                cmd.extend(["--print", "--dangerously-skip-permissions"])

            # MCP isolation via command-line flags (preserves auth)
            # CRIT-3 fix: Using --strict-mcp-config instead of CLAUDE_CONFIG_DIR
            if group == ExperimentGroup.CONTROL:
                # Strictly use empty MCP config - blocks all MCP servers
                empty_mcp = json.dumps({"mcpServers": {}})
                cmd.extend(["--strict-mcp-config", "--mcp-config", empty_mcp])
            else:
                # Treatment: add invar MCP if available
                mcp_config = self._get_treatment_mcp_config(quiet=quiet)
                if mcp_config:
                    cmd.extend(["--mcp-config", json.dumps(mcp_config)])

            # Build prompt with appropriate prefix for treatment group
            if group == ExperimentGroup.TREATMENT:
                if use_interactive:
                    # Interactive mode: Use skill trigger to invoke /develop via Skill tool
                    full_prompt = USBV_SKILL_PREFIX_INTERACTIVE + task.prompt
                else:
                    # Print mode: Embed full USBV guidance (no Skill tool available)
                    full_prompt = USBV_SKILL_PREFIX_PRINT + task.prompt
            else:
                full_prompt = task.prompt

            cmd.extend(["-p", full_prompt])

            # Run Claude Code
            if use_interactive:
                # Use PTY for interactive mode
                timeout = self.config.interactive_timeout
                return_code, stdout, stderr = self._run_interactive_pty(
                    cmd, workspace, timeout
                )
                result.conversation_log = stdout
                if stderr:
                    result.error_message = stderr
            else:
                # Use subprocess for print mode
                process = subprocess.run(
                    cmd,
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    timeout=self.config.timeout_seconds,
                )
                result.conversation_log = process.stdout
                if process.stderr:
                    result.error_message = process.stderr

            # Collect generated files from appropriate directory
            files_dir = repo_dir if is_swe_task else workspace
            result.generated_files = self._collect_generated_files(files_dir)

            # Run tests and collect metrics
            result.metrics = self.collector.collect(
                workspace=workspace,
                task=task,
                group=group,
                conversation_log=result.conversation_log,
                repo_dir=repo_dir if is_swe_task else None,
                use_docker=self.config.use_docker,
                docker_timeout=self.config.docker_timeout,
            )

            result.status = TaskStatus.COMPLETED
            result.end_time = datetime.now()

            # Calculate execution time (MAJ-3 fix)
            result.metrics.execution_time_seconds = (
                result.end_time - result.start_time
            ).total_seconds()

        except subprocess.TimeoutExpired:
            result.status = TaskStatus.TIMEOUT
            result.error_message = f"Task timed out after {self.config.timeout_seconds}s"
            result.end_time = datetime.now()

        except Exception as e:
            result.status = TaskStatus.FAILED
            result.error_message = str(e)
            result.end_time = datetime.now()

        return result

    def _get_treatment_mcp_config(self, quiet: bool = False) -> dict | None:
        """
        Get MCP configuration for treatment group.

        Args:
            quiet: Suppress warning messages

        Returns:
            dict with MCP servers if invar MCP is available, else None.

        Priority:
        1. uvx invar-tools mcp (recommended, isolated, no install needed)
        2. python -m invar.mcp (if invar installed locally)
        3. None (config files only)
        """
        # Option 1: uvx (recommended - isolated, always up-to-date)
        if shutil.which("uvx") is not None:
            return {
                "mcpServers": {
                    "invar": {
                        "command": "uvx",
                        "args": ["invar-tools", "mcp"],
                    }
                }
            }

        # Option 2: local invar installation
        try:
            import invar.mcp  # noqa: F401

            return {
                "mcpServers": {
                    "invar": {
                        "command": sys.executable,
                        "args": ["-m", "invar.mcp"],
                    }
                }
            }
        except ImportError:
            pass

        # Fallback: no MCP but still has CLAUDE.md/INVAR.md
        if not quiet:
            print("  Warning: invar MCP not found, treatment will use config files only")
        return None

    def _run_interactive_pty(
        self,
        cmd: list[str],
        workspace: Path,
        timeout: int,
    ) -> tuple[int, str, str]:
        """
        Run Claude in interactive mode using PTY simulation.

        This method creates a pseudo-terminal to allow Claude to run
        in interactive mode without blocking on TTY detection.

        Args:
            cmd: Command and arguments to execute
            workspace: Working directory
            timeout: Maximum execution time in seconds

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        master, slave = pty.openpty()

        process = subprocess.Popen(
            cmd,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            cwd=workspace,
        )
        os.close(slave)

        output_chunks: list[str] = []
        start_time = time.time()

        try:
            while True:
                # Check timeout
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    break

                # Check for available output
                ready, _, _ = select.select([master], [], [], 1.0)
                if ready:
                    try:
                        data = os.read(master, 4096).decode("utf-8", errors="replace")
                        if data:
                            output_chunks.append(data)

                            # Auto-respond to common prompts
                            if "Continue? [Y/n]" in data or "[Y/N]" in data:
                                os.write(master, b"Y\n")
                            elif "Choose option" in data:
                                os.write(master, b"1\n")
                    except OSError:
                        # PTY closed
                        break

                # Check if process completed
                if process.poll() is not None:
                    # Read any remaining output
                    try:
                        while True:
                            ready, _, _ = select.select([master], [], [], 0.1)
                            if not ready:
                                break
                            data = os.read(master, 4096).decode("utf-8", errors="replace")
                            if not data:
                                break
                            output_chunks.append(data)
                    except OSError:
                        pass
                    break

        finally:
            try:
                os.close(master)
            except OSError:
                pass

        output = "".join(output_chunks)
        return_code = process.returncode or 0

        return return_code, output, ""

    def _collect_generated_files(self, workspace: Path) -> dict[str, str]:
        """Collect all generated Python files from workspace."""
        files = {}

        for py_file in workspace.rglob("*.py"):
            # Skip __pycache__ and hidden files
            if "__pycache__" in str(py_file) or py_file.name.startswith("."):
                continue

            relative_path = py_file.relative_to(workspace)
            files[str(relative_path)] = py_file.read_text()

        return files

    def run_experiment(
        self,
        tasks: list[Task] | None = None,
        groups: list[ExperimentGroup] | None = None,
        use_rich: bool = True,
    ) -> ExperimentResult:
        """
        Run a complete experiment.

        Args:
            tasks: Tasks to run (defaults to all)
            groups: Groups to run (defaults to both)
            use_rich: Use Rich progress display (default True)

        Returns:
            ExperimentResult with all results
        """
        if tasks is None:
            tasks = self.load_tasks()

        if groups is None:
            groups = [ExperimentGroup.CONTROL, ExperimentGroup.TREATMENT]

        # Create experiment
        experiment_id = datetime.now().strftime("exp_%Y%m%d_%H%M%S")
        experiment = ExperimentResult(
            experiment_id=experiment_id,
            start_time=datetime.now(),
            config_snapshot=create_experiment_metadata(self.config),
        )

        if use_rich:
            self._run_with_rich_display(tasks, groups, experiment)
        else:
            self._run_with_simple_display(tasks, groups, experiment)

        experiment.end_time = datetime.now()

        # Save results
        self._save_results(experiment, use_rich=use_rich)

        return experiment

    def _run_with_rich_display(
        self,
        tasks: list[Task],
        groups: list[ExperimentGroup],
        experiment: ExperimentResult,
    ) -> None:
        """Run experiment with Rich progress visualization."""
        # Lazy import to avoid requiring rich for simple commands
        from harness.display import ProgressDisplay

        with ProgressDisplay(tasks) as display:
            for task in tasks:
                for group in groups:
                    # Mark as running
                    display.mark_task_running(task.id, group)

                    # Run the task
                    result = self.run_task(task, group, quiet=True)
                    experiment.add_result(result)

                    # Mark as completed
                    display.mark_task_completed(task.id, group, result)

    def _run_with_simple_display(
        self,
        tasks: list[Task],
        groups: list[ExperimentGroup],
        experiment: ExperimentResult,
    ) -> None:
        """Run experiment with simple print-based progress."""
        total = len(tasks) * len(groups)
        current = 0

        for task in tasks:
            for group in groups:
                current += 1
                print(f"[{current}/{total}] Running {task.id} ({group.value})...")

                result = self.run_task(task, group, quiet=False)
                experiment.add_result(result)

                # Print status
                status_icon = "✓" if result.status == TaskStatus.COMPLETED else "✗"
                print(f"  {status_icon} {result.status.value}")

    def _save_results(self, experiment: ExperimentResult, use_rich: bool = False) -> None:
        """Save experiment results to disk."""
        from rich.console import Console
        from rich.panel import Panel

        results_dir = self.config.results_dir / experiment.experiment_id
        results_dir.mkdir(parents=True, exist_ok=True)

        # Save summary
        summary = experiment.get_summary()
        with open(results_dir / "summary.json", "w") as f:
            json.dump(summary, f, indent=2)

        # Save detailed results
        all_results = {
            "experiment_id": experiment.experiment_id,
            "start_time": experiment.start_time.isoformat(),
            "end_time": experiment.end_time.isoformat() if experiment.end_time else None,
            "config": experiment.config_snapshot,
            "control_results": [r.to_dict() for r in experiment.control_results],
            "treatment_results": [r.to_dict() for r in experiment.treatment_results],
        }

        with open(results_dir / "results.json", "w") as f:
            json.dump(all_results, f, indent=2)

        if use_rich:
            console = Console()
            console.print()
            console.print(Panel(
                f"[green]Results saved to:[/green]\n{results_dir}",
                title="[bold]Complete[/bold]",
                border_style="green",
            ))
        else:
            print(f"\nResults saved to: {results_dir}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Invar Benchmark Runner")

    parser.add_argument(
        "--group",
        choices=["control", "treatment", "both"],
        default="both",
        help="Which group(s) to run",
    )

    parser.add_argument(
        "--tier",
        choices=["tier1_standard", "tier2_contracts", "tier3_integration", "tier4_swe"],
        help="Filter tasks by tier",
    )

    parser.add_argument(
        "--task",
        help="Run a specific task by ID",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Timeout per task in seconds",
    )

    parser.add_argument(
        "--model",
        choices=["opus", "sonnet", "haiku"],
        default="sonnet",
        help="Claude model to use: opus, sonnet, haiku (default: sonnet)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List tasks without running",
    )

    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable Rich progress display (use simple text output)",
    )

    parser.add_argument(
        "--mode",
        choices=["print", "interactive"],
        default="print",
        help="Execution mode: 'print' (single-shot) or 'interactive' (PTY-based)",
    )

    parser.add_argument(
        "--max-turns",
        type=int,
        default=50,
        help="Max turns for interactive mode (default: 50)",
    )

    parser.add_argument(
        "--interactive-timeout",
        type=int,
        default=600,
        help="Timeout for interactive mode in seconds (default: 600)",
    )

    # Cache management (BM-03)
    parser.add_argument(
        "--cache-stats",
        action="store_true",
        help="Show repository cache statistics and exit",
    )

    parser.add_argument(
        "--cache-clear",
        nargs="?",
        const="all",
        metavar="REPO",
        help="Clear cache. Specify REPO (e.g., 'astropy/astropy') or omit for all",
    )

    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable repository caching for this run",
    )

    # Docker evaluation (BM-03 Phase 2)
    parser.add_argument(
        "--docker",
        action="store_true",
        help="Use Docker for SWE-bench evaluation (requires swebench and Docker)",
    )

    parser.add_argument(
        "--docker-timeout",
        type=int,
        default=1800,
        help="Timeout for Docker evaluation in seconds (default: 1800)",
    )

    parser.add_argument(
        "--check-docker",
        action="store_true",
        help="Check Docker and swebench availability and exit",
    )

    args = parser.parse_args()

    # Handle check-docker command first
    if args.check_docker:
        from harness.docker_runner import check_docker_available, check_swebench_available

        docker_ok, docker_msg = check_docker_available()
        swe_ok, swe_msg = check_swebench_available()

        print("Docker Integration Status:")
        print(f"  Docker: {'✓' if docker_ok else '✗'} {docker_msg}")
        print(f"  swebench: {'✓' if swe_ok else '✗'} {swe_msg}")

        if docker_ok and swe_ok:
            print("\n✓ Ready for Docker-based SWE evaluation")
        else:
            print("\n✗ Docker evaluation not available")
            print("  Install: pip install 'invar-benchmark[docker]'")
        return

    # Create config
    config = BenchmarkConfig(
        timeout_seconds=args.timeout,
        claude_model=args.model,
        execution_mode=args.mode,
        max_turns=args.max_turns,
        interactive_timeout=args.interactive_timeout,
        use_repo_cache=not args.no_cache,
        use_docker=args.docker,
        docker_timeout=args.docker_timeout,
    )

    # Handle cache commands
    if args.cache_stats:
        stats = get_cache_stats(config)
        print(f"Cache directory: {stats['cache_dir']}")
        print(f"Total size: {stats['total_size_mb']:.2f} MB")
        print(f"Cached repositories: {len(stats['repos'])}")
        for repo in stats["repos"]:
            print(f"  - {repo['name']}: {repo['size_mb']:.2f} MB")
        return

    if args.cache_clear:
        repo_arg = None if args.cache_clear == "all" else args.cache_clear
        cleared = clear_cache(config, repo=repo_arg)
        if repo_arg:
            print(f"Cleared cache for {repo_arg}" if cleared else f"No cache found for {repo_arg}")
        else:
            print(f"Cleared {cleared} cached repositories")
        return

    # Create runner
    runner = BenchmarkRunner(config)

    # Load tasks
    tasks = runner.load_tasks(tier=args.tier)

    if args.task:
        tasks = [t for t in tasks if t.id == args.task]
        if not tasks:
            print(f"Task not found: {args.task}")
            sys.exit(1)

    if args.dry_run:
        print(f"Found {len(tasks)} tasks:")
        for task in tasks:
            print(f"  - {task.id}: {task.name} ({task.tier.value})")
        return

    # Determine groups
    if args.group == "control":
        groups = [ExperimentGroup.CONTROL]
    elif args.group == "treatment":
        groups = [ExperimentGroup.TREATMENT]
    else:
        groups = [ExperimentGroup.CONTROL, ExperimentGroup.TREATMENT]

    # Run experiment
    use_rich = not args.no_progress

    # Display mode info
    mode_info = f"Mode: {args.mode}"
    if args.mode == "interactive":
        mode_info += f" (max_turns={args.max_turns}, timeout={args.interactive_timeout}s)"

    if not use_rich:
        print(f"Running {len(tasks)} tasks for {len(groups)} group(s)...")
        print(f"  {mode_info}")

    experiment = runner.run_experiment(tasks=tasks, groups=groups, use_rich=use_rich)

    # Print summary
    summary = experiment.get_summary()

    if use_rich:
        _print_rich_summary(summary)
    else:
        _print_simple_summary(summary)


def _print_simple_summary(summary: dict) -> None:
    """Print simple text summary."""
    print("\n" + "=" * 60)
    print("EXPERIMENT SUMMARY")
    print("=" * 60)

    for group_name in ["control", "treatment"]:
        if group_name in summary and summary[group_name]:
            stats = summary[group_name]
            print(f"\n{group_name.upper()}:")
            print(f"  Completed: {stats['completed']}/{stats['total_tasks']}")
            print(f"  Avg Test Pass Rate: {stats['avg_test_pass_rate']:.1%}")
            print(f"  Avg Hidden Test Rate: {stats['avg_hidden_test_pass_rate']:.1%}")
            print(f"  Avg Iterations: {stats['avg_iterations']:.1f}")
            print(f"  Avg Tokens: {stats['avg_tokens']:.0f}")


def _print_rich_summary(summary: dict) -> None:
    """Print Rich formatted summary."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel

    console = Console()

    # Create comparison table
    table = Table(
        title="Experiment Results",
        show_header=True,
        header_style="bold",
        border_style="blue",
    )

    table.add_column("Metric", style="cyan")
    table.add_column("Control", justify="right")
    table.add_column("Treatment", justify="right")
    table.add_column("Delta", justify="right")

    control = summary.get("control", {})
    treatment = summary.get("treatment", {})

    def format_delta(c: float, t: float, higher_is_better: bool = True) -> str:
        if c == 0 and t == 0:
            return "[dim]--[/dim]"
        delta = t - c
        pct = (delta / c * 100) if c != 0 else 0
        color = "green" if (delta > 0) == higher_is_better else "red" if delta != 0 else "dim"
        sign = "+" if delta > 0 else ""
        return f"[{color}]{sign}{pct:.1f}%[/{color}]"

    if control and treatment:
        # Completed
        table.add_row(
            "Completed",
            f"{control.get('completed', 0)}/{control.get('total_tasks', 0)}",
            f"{treatment.get('completed', 0)}/{treatment.get('total_tasks', 0)}",
            "[dim]--[/dim]",
        )

        # Test Pass Rate
        c_rate = control.get("avg_test_pass_rate", 0)
        t_rate = treatment.get("avg_test_pass_rate", 0)
        table.add_row(
            "Test Pass Rate",
            f"{c_rate:.1%}",
            f"{t_rate:.1%}",
            format_delta(c_rate, t_rate, higher_is_better=True),
        )

        # Hidden Test Rate
        c_hidden = control.get("avg_hidden_test_pass_rate", 0)
        t_hidden = treatment.get("avg_hidden_test_pass_rate", 0)
        table.add_row(
            "Hidden Test Rate",
            f"{c_hidden:.1%}",
            f"{t_hidden:.1%}",
            format_delta(c_hidden, t_hidden, higher_is_better=True),
        )

        # Iterations
        c_iter = control.get("avg_iterations", 0)
        t_iter = treatment.get("avg_iterations", 0)
        table.add_row(
            "Avg Iterations",
            f"{c_iter:.1f}",
            f"{t_iter:.1f}",
            format_delta(c_iter, t_iter, higher_is_better=False),
        )

        # Tokens
        c_tokens = control.get("avg_tokens", 0)
        t_tokens = treatment.get("avg_tokens", 0)
        table.add_row(
            "Avg Tokens",
            f"{c_tokens:.0f}",
            f"{t_tokens:.0f}",
            format_delta(c_tokens, t_tokens, higher_is_better=False),
        )

    console.print()
    console.print(table)


if __name__ == "__main__":
    main()
