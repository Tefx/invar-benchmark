"""
Configuration management for benchmark framework.
"""

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BenchmarkConfig:
    """Configuration for benchmark experiments."""

    # Paths
    benchmark_root: Path = field(default_factory=lambda: Path.home() / "Projects" / "invar-benchmark")
    invar_project: Path = field(default_factory=lambda: Path.home() / "Projects" / "Invar")

    # Experiment settings
    max_iterations: int = 10
    timeout_seconds: int = 600  # 10 minutes per task
    parallel_tasks: int = 1  # Sequential by default

    # Claude Code settings
    claude_command: str = "claude"
    claude_model: str = "sonnet"  # Model: "opus", "sonnet", "haiku", or full name
    use_print_mode: bool = True  # Deprecated: use execution_mode instead

    # Execution mode settings (BM-02)
    execution_mode: str = "print"  # "print" | "interactive"
    max_turns: int = 200  # Max turns for interactive mode
    interactive_timeout: int = 600  # Timeout for interactive mode (seconds)

    # Routing mode settings (BM-05: Fair Benchmark)
    # natural_routing=True: No explicit /develop prefix, let CLAUDE.md routing rules activate
    # natural_routing=False: Force /develop prefix (legacy, for debugging only)
    natural_routing: bool = True  # Default: fair benchmark mode

    # SWE-bench settings (BM-03)
    use_repo_cache: bool = True  # Cache bare repos for faster subsequent runs
    use_docker: bool = False  # Use Docker for SWE task execution
    docker_timeout: int = 1800  # Docker evaluation timeout in seconds

    @property
    def configs_dir(self) -> Path:
        """Directory containing group configurations."""
        return self.benchmark_root / "configs"

    @property
    def control_config(self) -> Path:
        """Control group config directory."""
        return self.configs_dir / "control"

    @property
    def treatment_config(self) -> Path:
        """Treatment group config directory."""
        return self.configs_dir / "treatment"

    @property
    def tasks_dir(self) -> Path:
        """Directory containing task definitions."""
        return self.benchmark_root / "tasks"

    @property
    def workspace_dir(self) -> Path:
        """Directory for task execution."""
        return self.benchmark_root / "workspace"

    @property
    def results_dir(self) -> Path:
        """Directory for results storage."""
        return self.benchmark_root / "results"

    @property
    def cache_dir(self) -> Path:
        """Directory for caching (bare repos, Docker images, etc.)."""
        return self.benchmark_root / ".cache"

    @property
    def bare_repos_dir(self) -> Path:
        """Directory for cached bare git repositories."""
        return self.cache_dir / "bare_repos"

    def get_workspace_path(self, group: str, task_id: str) -> Path:
        """Get workspace path for a specific task and group."""
        return self.workspace_dir / group / task_id

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "benchmark_root": str(self.benchmark_root),
            "invar_project": str(self.invar_project),
            "max_iterations": self.max_iterations,
            "timeout_seconds": self.timeout_seconds,
            "parallel_tasks": self.parallel_tasks,
            "claude_command": self.claude_command,
            "claude_model": self.claude_model,
            "use_print_mode": self.use_print_mode,
            "execution_mode": self.execution_mode,
            "max_turns": self.max_turns,
            "interactive_timeout": self.interactive_timeout,
            "natural_routing": self.natural_routing,
            "use_repo_cache": self.use_repo_cache,
            "use_docker": self.use_docker,
            "docker_timeout": self.docker_timeout,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchmarkConfig":
        """Create from dictionary."""
        return cls(
            benchmark_root=Path(data.get("benchmark_root", ".")),
            invar_project=Path(data.get("invar_project", ".")),
            max_iterations=data.get("max_iterations", 10),
            timeout_seconds=data.get("timeout_seconds", 600),
            parallel_tasks=data.get("parallel_tasks", 1),
            claude_command=data.get("claude_command", "claude"),
            claude_model=data.get("claude_model", "sonnet"),
            use_print_mode=data.get("use_print_mode", True),
            execution_mode=data.get("execution_mode", "print"),
            max_turns=data.get("max_turns", 50),
            interactive_timeout=data.get("interactive_timeout", 600),
            natural_routing=data.get("natural_routing", True),
            use_repo_cache=data.get("use_repo_cache", True),
            use_docker=data.get("use_docker", False),
            docker_timeout=data.get("docker_timeout", 1800),
        )


def setup_workspace(
    config: BenchmarkConfig,
    group: str,
    task_id: str,
    initial_files: dict[str, str],
) -> Path:
    """
    Set up an isolated workspace for a task.

    Args:
        config: Benchmark configuration
        group: 'control' or 'treatment'
        task_id: Task identifier
        initial_files: Initial files to copy to workspace

    Returns:
        Path to the workspace directory
    """
    workspace = config.get_workspace_path(group, task_id)

    # Clean existing workspace
    if workspace.exists():
        shutil.rmtree(workspace)

    workspace.mkdir(parents=True)

    # Create src directories
    (workspace / "src" / "core").mkdir(parents=True)
    (workspace / "src" / "shell").mkdir(parents=True)
    (workspace / "tests").mkdir(parents=True)

    # Copy group-specific config
    if group == "control":
        src_config = config.control_config
    else:
        src_config = config.treatment_config

    # Copy CLAUDE.md
    claude_md = src_config / "CLAUDE.md"
    if claude_md.exists():
        shutil.copy(claude_md, workspace / "CLAUDE.md")

    # For treatment, copy additional Invar files
    if group == "treatment":
        # Copy INVAR.md
        invar_md = src_config / "INVAR.md"
        if invar_md.exists():
            shutil.copy(invar_md, workspace / "INVAR.md")

        # Copy .invar directory
        invar_dir = src_config / ".invar"
        if invar_dir.exists():
            shutil.copytree(invar_dir, workspace / ".invar")

    # Write initial task files
    for file_path, content in initial_files.items():
        full_path = workspace / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

    # Initialize git repo for tracking changes
    import subprocess

    try:
        subprocess.run(
            ["git", "init"],
            cwd=workspace,
            capture_output=True,
            check=True,
        )

        # Configure local git user for this repo (CRIT-2 fix)
        # This avoids requiring global git config
        subprocess.run(
            ["git", "config", "user.email", "benchmark@invar.local"],
            cwd=workspace,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Invar Benchmark"],
            cwd=workspace,
            capture_output=True,
            check=True,
        )

        subprocess.run(
            ["git", "add", "."],
            cwd=workspace,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial task setup"],
            cwd=workspace,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        # Git initialization is optional - continue without it
        pass

    return workspace


def _get_or_create_bare_repo(config: BenchmarkConfig, repo: str) -> Path:
    """
    Get or create a cached bare repository.

    Args:
        config: Benchmark configuration
        repo: Repository name (e.g., "astropy/astropy")

    Returns:
        Path to the bare repository

    Raises:
        RuntimeError: If clone fails
    """
    import subprocess

    # Create cache directory if needed
    config.bare_repos_dir.mkdir(parents=True, exist_ok=True)

    # Bare repo path: astropy/astropy -> astropy__astropy.git
    bare_name = repo.replace("/", "__") + ".git"
    bare_path = config.bare_repos_dir / bare_name

    repo_url = f"https://github.com/{repo}.git"

    if bare_path.exists():
        # Update existing bare repo
        try:
            subprocess.run(
                ["git", "fetch", "--all", "--prune"],
                cwd=bare_path,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            # Fetch failure is not critical - continue with cached version
            pass
    else:
        # Create new bare clone
        try:
            subprocess.run(
                ["git", "clone", "--bare", "--filter=blob:none", repo_url, str(bare_path)],
                capture_output=True,
                text=True,
                check=True,
                timeout=300,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to clone {repo}: {e.stderr}")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Clone timeout for {repo}")

    return bare_path


def _create_worktree(bare_path: Path, worktree_path: Path, commit: str) -> None:
    """
    Create a git worktree from a bare repository.

    Args:
        bare_path: Path to bare repository
        worktree_path: Path for the worktree
        commit: Commit hash to checkout
    """
    import subprocess

    # Remove existing worktree directory if any
    if worktree_path.exists():
        shutil.rmtree(worktree_path)

    # Prune stale worktrees (fixes "already registered worktree" errors)
    subprocess.run(
        ["git", "worktree", "prune"],
        cwd=bare_path,
        capture_output=True,
    )

    # Create worktree at specific commit
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(worktree_path), commit],
        cwd=bare_path,
        capture_output=True,
        text=True,
        check=True,
    )

    # Configure local git user in worktree
    subprocess.run(
        ["git", "config", "user.email", "benchmark@invar.local"],
        cwd=worktree_path,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Invar Benchmark"],
        cwd=worktree_path,
        capture_output=True,
    )


def setup_swe_workspace(
    config: BenchmarkConfig,
    group: str,
    task_id: str,
    swe_metadata: dict[str, Any],
) -> Path:
    """
    Set up workspace for SWE-bench task.

    Uses cached bare repos when use_repo_cache=True for faster subsequent runs.
    Falls back to direct clone when cache is disabled.

    Args:
        config: Benchmark configuration
        group: 'control' or 'treatment'
        task_id: Task identifier
        swe_metadata: SWE-bench metadata with repo, base_commit, etc.

    Returns:
        Path to the workspace directory

    Raises:
        RuntimeError: If git clone or checkout fails
    """
    import subprocess

    workspace = config.get_workspace_path(group, task_id)

    # Clean existing workspace
    if workspace.exists():
        shutil.rmtree(workspace)

    workspace.mkdir(parents=True)

    repo = swe_metadata.get("repo", "")
    base_commit = swe_metadata.get("base_commit", "")

    if not repo:
        raise RuntimeError(f"SWE task {task_id} missing repo in metadata")

    repo_dir = workspace / "repo"

    if config.use_repo_cache:
        # Use cached bare repo + worktree (fast for repeated runs)
        try:
            bare_path = _get_or_create_bare_repo(config, repo)
            _create_worktree(bare_path, repo_dir, base_commit or "HEAD")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to create worktree for {repo}@{base_commit}: {e.stderr}")
    else:
        # Direct clone (no caching)
        repo_url = f"https://github.com/{repo}.git"

        try:
            subprocess.run(
                ["git", "clone", "--no-checkout", "--filter=blob:none", repo_url, str(repo_dir)],
                capture_output=True,
                text=True,
                check=True,
                timeout=300,
            )

            if base_commit:
                subprocess.run(
                    ["git", "checkout", base_commit],
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                    check=True,
                )

            subprocess.run(
                ["git", "config", "user.email", "benchmark@invar.local"],
                cwd=repo_dir,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Invar Benchmark"],
                cwd=repo_dir,
                capture_output=True,
            )

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to clone/checkout {repo}@{base_commit}: {e.stderr}")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Clone timeout for {repo}")

    # Optional: Install dependencies
    has_setup = (repo_dir / "setup.py").exists() or (repo_dir / "pyproject.toml").exists()
    if has_setup:
        try:
            subprocess.run(
                ["pip", "install", "-e", ".", "--quiet"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass

    # Copy group-specific config to workspace (not repo dir)
    if group == "control":
        src_config = config.control_config
    else:
        src_config = config.treatment_config

    # Copy CLAUDE.md to workspace root
    claude_md = src_config / "CLAUDE.md"
    if claude_md.exists():
        shutil.copy(claude_md, workspace / "CLAUDE.md")

    # For treatment, copy additional Invar files
    if group == "treatment":
        invar_md = src_config / "INVAR.md"
        if invar_md.exists():
            shutil.copy(invar_md, workspace / "INVAR.md")

        invar_dir = src_config / ".invar"
        if invar_dir.exists():
            shutil.copytree(invar_dir, workspace / ".invar")

    # Create tests directory for hidden tests
    (workspace / "tests").mkdir(exist_ok=True)

    return workspace


def get_cache_stats(config: BenchmarkConfig) -> dict[str, Any]:
    """
    Get statistics about the repository cache.

    Args:
        config: Benchmark configuration

    Returns:
        Dictionary with cache statistics
    """
    stats = {
        "cache_dir": str(config.cache_dir),
        "repos": [],
        "total_size_mb": 0,
    }

    if not config.bare_repos_dir.exists():
        return stats

    for repo_path in config.bare_repos_dir.iterdir():
        if repo_path.is_dir() and repo_path.name.endswith(".git"):
            # Calculate size
            size_bytes = sum(f.stat().st_size for f in repo_path.rglob("*") if f.is_file())
            size_mb = size_bytes / (1024 * 1024)

            # Get repo name from path
            repo_name = repo_path.name.replace("__", "/").replace(".git", "")

            stats["repos"].append({
                "name": repo_name,
                "path": str(repo_path),
                "size_mb": round(size_mb, 2),
            })
            stats["total_size_mb"] += size_mb

    stats["total_size_mb"] = round(stats["total_size_mb"], 2)
    return stats


def clear_cache(config: BenchmarkConfig, repo: str | None = None) -> int:
    """
    Clear the repository cache.

    Args:
        config: Benchmark configuration
        repo: Specific repo to clear (e.g., "astropy/astropy"), or None for all

    Returns:
        Number of repos cleared
    """
    import subprocess

    if not config.bare_repos_dir.exists():
        return 0

    cleared = 0

    if repo:
        # Clear specific repo
        bare_name = repo.replace("/", "__") + ".git"
        bare_path = config.bare_repos_dir / bare_name

        if bare_path.exists():
            # Clean up worktrees first
            try:
                subprocess.run(
                    ["git", "worktree", "prune"],
                    cwd=bare_path,
                    capture_output=True,
                )
            except Exception:
                pass

            shutil.rmtree(bare_path)
            cleared = 1
    else:
        # Clear all repos
        for repo_path in config.bare_repos_dir.iterdir():
            if repo_path.is_dir() and repo_path.name.endswith(".git"):
                try:
                    subprocess.run(
                        ["git", "worktree", "prune"],
                        cwd=repo_path,
                        capture_output=True,
                    )
                except Exception:
                    pass

                shutil.rmtree(repo_path)
                cleared += 1

    return cleared


def get_config_hash(config_dir: Path) -> str:
    """
    Calculate hash of configuration files for versioning.

    Args:
        config_dir: Directory containing config files

    Returns:
        SHA256 hash of all config files
    """
    hasher = hashlib.sha256()

    for file_path in sorted(config_dir.rglob("*")):
        if file_path.is_file() and not file_path.name.startswith("."):
            hasher.update(file_path.read_bytes())

    return hasher.hexdigest()[:12]


def create_experiment_metadata(config: BenchmarkConfig) -> dict[str, Any]:
    """
    Create experiment metadata for reproducibility.

    Args:
        config: Benchmark configuration

    Returns:
        Dictionary with experiment metadata
    """
    import subprocess
    from datetime import datetime

    # Get Claude Code version
    try:
        result = subprocess.run(
            [config.claude_command, "--version"],
            capture_output=True,
            text=True,
        )
        claude_version = result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        claude_version = "unknown"

    # Get Invar version
    try:
        result = subprocess.run(
            ["invar", "--version"],
            capture_output=True,
            text=True,
        )
        invar_version = result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        invar_version = "unknown"

    return {
        "timestamp": datetime.now().isoformat(),
        "claude_code_version": claude_version,
        "invar_version": invar_version,
        "config": config.to_dict(),
        "config_hashes": {
            "control": get_config_hash(config.control_config),
            "treatment": get_config_hash(config.treatment_config),
        },
    }
