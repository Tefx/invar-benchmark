"""
Progress visualization for benchmark runner.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

from harness.models import ExperimentGroup, Task, TaskResult, TaskStatus


@dataclass
class TaskProgress:
    """Tracks progress for a single task across groups."""

    task: Task
    control_result: TaskResult | None = None
    treatment_result: TaskResult | None = None
    control_status: str = "pending"  # pending, running, completed, failed
    treatment_status: str = "pending"

    def get_control_display(self) -> str:
        """Get display string for control group."""
        if self.control_status == "pending":
            return "[dim]○ pending[/dim]"
        elif self.control_status == "running":
            return "[yellow]⏳ running...[/yellow]"
        elif self.control_result:
            rate = self.control_result.metrics.test_pass_rate
            tokens = self.control_result.metrics.total_tokens
            if self.control_result.status == TaskStatus.COMPLETED:
                color = "green" if rate == 1.0 else "yellow" if rate > 0 else "red"
                return f"[{color}]✓ {rate:.0%}[/{color}] [dim]({tokens}t)[/dim]"
            elif self.control_result.status == TaskStatus.FAILED:
                return "[red]✗ failed[/red]"
            elif self.control_result.status == TaskStatus.TIMEOUT:
                return "[red]⏱ timeout[/red]"
        return "[dim]○[/dim]"

    def get_treatment_display(self) -> str:
        """Get display string for treatment group."""
        if self.treatment_status == "pending":
            return "[dim]○ pending[/dim]"
        elif self.treatment_status == "running":
            return "[yellow]⏳ running...[/yellow]"
        elif self.treatment_result:
            rate = self.treatment_result.metrics.test_pass_rate
            tokens = self.treatment_result.metrics.total_tokens
            if self.treatment_result.status == TaskStatus.COMPLETED:
                color = "green" if rate == 1.0 else "yellow" if rate > 0 else "red"
                return f"[{color}]✓ {rate:.0%}[/{color}] [dim]({tokens}t)[/dim]"
            elif self.treatment_result.status == TaskStatus.FAILED:
                return "[red]✗ failed[/red]"
            elif self.treatment_result.status == TaskStatus.TIMEOUT:
                return "[red]⏱ timeout[/red]"
        return "[dim]○[/dim]"


@dataclass
class BenchmarkProgress:
    """Tracks overall benchmark progress."""

    tasks: list[Task]
    task_progress: dict[str, TaskProgress] = field(default_factory=dict)
    current_task: str = ""
    current_group: str = ""
    start_time: datetime = field(default_factory=datetime.now)
    completed_count: int = 0
    total_count: int = 0

    def __post_init__(self) -> None:
        """Initialize task progress tracking."""
        for task in self.tasks:
            self.task_progress[task.id] = TaskProgress(task=task)
        # Total = tasks * 2 (control + treatment)
        self.total_count = len(self.tasks) * 2

    def mark_running(self, task_id: str, group: ExperimentGroup) -> None:
        """Mark a task as running."""
        self.current_task = task_id
        self.current_group = group.value
        if task_id in self.task_progress:
            if group == ExperimentGroup.CONTROL:
                self.task_progress[task_id].control_status = "running"
            else:
                self.task_progress[task_id].treatment_status = "running"

    def mark_completed(
        self, task_id: str, group: ExperimentGroup, result: TaskResult
    ) -> None:
        """Mark a task as completed with result."""
        self.completed_count += 1
        if task_id in self.task_progress:
            if group == ExperimentGroup.CONTROL:
                self.task_progress[task_id].control_status = "completed"
                self.task_progress[task_id].control_result = result
            else:
                self.task_progress[task_id].treatment_status = "completed"
                self.task_progress[task_id].treatment_result = result

    def get_group_stats(self, group: ExperimentGroup) -> dict[str, Any]:
        """Get statistics for a group."""
        results = []
        for tp in self.task_progress.values():
            if group == ExperimentGroup.CONTROL and tp.control_result:
                results.append(tp.control_result)
            elif group == ExperimentGroup.TREATMENT and tp.treatment_result:
                results.append(tp.treatment_result)

        if not results:
            return {"completed": 0, "total": len(self.tasks), "pass_rate": 0, "tokens": 0}

        completed = [r for r in results if r.status == TaskStatus.COMPLETED]
        avg_pass = (
            sum(r.metrics.test_pass_rate for r in completed) / len(completed)
            if completed
            else 0
        )
        avg_tokens = (
            sum(r.metrics.total_tokens for r in completed) / len(completed)
            if completed
            else 0
        )

        return {
            "completed": len(completed),
            "total": len(self.tasks),
            "pass_rate": avg_pass,
            "tokens": avg_tokens,
        }


class ProgressDisplay:
    """Rich-based progress display for benchmark runner."""

    def __init__(self, tasks: list[Task]) -> None:
        self.console = Console()
        self.progress_data = BenchmarkProgress(tasks=tasks)
        self.live: Live | None = None

        # Create progress bar
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeElapsedColumn(),
            TextColumn("│"),
            TimeRemainingColumn(),
            console=self.console,
        )
        self.main_task: TaskID | None = None

    def _build_header_panel(self) -> Panel:
        """Build the header panel with progress bar."""
        current = self.progress_data.current_task
        group = self.progress_data.current_group
        completed = self.progress_data.completed_count
        total = self.progress_data.total_count

        if completed == total:
            status_text = Text("✓ Complete", style="bold green")
        elif current:
            status_text = Text()
            status_text.append("▶ Running: ", style="yellow")
            status_text.append(f"{current} ({group})")
        else:
            status_text = Text("Waiting...", style="dim")

        content = Group(self.progress, status_text)

        return Panel(
            content,
            title="[bold]Invar Benchmark[/bold]",
            border_style="blue",
        )

    def _build_task_table(self) -> Table:
        """Build the task status table."""
        table = Table(
            show_header=True,
            header_style="bold",
            border_style="dim",
            expand=True,
        )

        table.add_column("Task", style="cyan", no_wrap=True)
        table.add_column("Control", justify="center")
        table.add_column("Treatment", justify="center")
        table.add_column("Tier", justify="center", style="dim")

        for task in self.progress_data.tasks:
            tp = self.progress_data.task_progress[task.id]
            tier = task.tier.value.split("_")[0]  # tier1 or tier2

            # Highlight current task
            task_name = task.id
            if task.id == self.progress_data.current_task:
                task_name = f"[bold yellow]{task.id}[/bold yellow]"

            table.add_row(
                task_name,
                tp.get_control_display(),
                tp.get_treatment_display(),
                tier,
            )

        return table

    def _build_summary_panel(self) -> Panel:
        """Build the running summary panel."""
        control_stats = self.progress_data.get_group_stats(ExperimentGroup.CONTROL)
        treatment_stats = self.progress_data.get_group_stats(ExperimentGroup.TREATMENT)

        def format_stats(name: str, stats: dict, color: str) -> str:
            completed = stats["completed"]
            total = stats["total"]
            pass_rate = stats["pass_rate"]
            tokens = stats["tokens"]

            rate_str = f"{pass_rate:.0%}" if completed > 0 else "--"
            tokens_str = f"{tokens:.0f}" if completed > 0 else "--"

            return (
                f"[{color}]{name}:[/{color}]  "
                f"{completed}/{total} done │ "
                f"{rate_str} pass │ "
                f"avg {tokens_str} tokens"
            )

        lines = [
            format_stats("Control  ", control_stats, "blue"),
            format_stats("Treatment", treatment_stats, "magenta"),
        ]

        return Panel(
            "\n".join(lines),
            title="[bold]Running Summary[/bold]",
            border_style="green",
        )

    def _build_display(self) -> Group:
        """Build the complete display."""
        return Group(
            self._build_header_panel(),
            self._build_task_table(),
            self._build_summary_panel(),
        )

    def start(self) -> None:
        """Start the live display."""
        self.main_task = self.progress.add_task(
            "Running benchmark...",
            total=self.progress_data.total_count,
        )
        self.live = Live(
            self._build_display(),
            console=self.console,
            refresh_per_second=4,
            transient=False,
        )
        self.live.start()

    def stop(self) -> None:
        """Stop the live display."""
        if self.live:
            self.live.stop()

    def update(self) -> None:
        """Update the display."""
        if self.live and self.main_task is not None:
            self.progress.update(
                self.main_task,
                completed=self.progress_data.completed_count,
            )
            self.live.update(self._build_display())

    def mark_task_running(self, task_id: str, group: ExperimentGroup) -> None:
        """Mark a task as running and update display."""
        self.progress_data.mark_running(task_id, group)
        self.update()

    def mark_task_completed(
        self, task_id: str, group: ExperimentGroup, result: TaskResult
    ) -> None:
        """Mark a task as completed and update display."""
        self.progress_data.mark_completed(task_id, group, result)
        self.update()

    def __enter__(self) -> "ProgressDisplay":
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.stop()
