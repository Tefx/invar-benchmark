# BM-03: SWE-Bench Integration Improvements

## Status: All Phases Implemented ✅

## Problem

Current SWE-bench integration has three key limitations:

| Limitation | Impact | Current State |
|-----------|--------|---------------|
| Clone/build time | 5-15 min/task | Shallow clone + pip install |
| System dependencies | Tests may fail | No isolation |
| Reproducibility | Inconsistent results | Host machine execution |

## Root Cause Analysis

### 1. Clone Time Issue

**Current flow:**
```
git clone --no-checkout --filter=blob:none → checkout base_commit → pip install -e .
```

**Problems:**
- Each task clones the full repo (even with filter)
- Same repo cloned multiple times across tasks
- No caching between runs

### 2. Dependency Issue

**Current flow:**
```python
subprocess.run(["pip", "install", "-e", ".", "--quiet"])
```

**Problems:**
- C extensions need compilers (gcc, clang)
- Version conflicts with host packages
- Missing system libraries (libffi, openssl-dev)
- Python version mismatches

### 3. Reproducibility Issue

**Problems:**
- Different results on different machines
- Host environment contamination
- No isolation between tasks

## Proposed Solutions

### Phase 1: Repository Caching (Quick Win) ✅ IMPLEMENTED

**Effort:** Low (1-2 days)
**Impact:** 80% reduction in clone time for repeated runs

**Approach:**
```
.cache/
├── bare_repos/
│   ├── astropy__astropy.git     # Bare clone (cached)
│   ├── django__django.git
│   └── ...
```

**Implementation (harness/config.py):**
- `_get_or_create_bare_repo()`: Creates/updates bare repo cache
- `_create_worktree()`: Creates detached worktree from bare repo
- `setup_swe_workspace()`: Uses cache when `use_repo_cache=True`
- `get_cache_stats()`: Returns cache size and repo list
- `clear_cache()`: Clears specific repo or all cached repos

**CLI Options (harness/runner.py):**
```bash
# Show cache statistics
python -m harness.runner --cache-stats

# Clear specific repo cache
python -m harness.runner --cache-clear astropy/astropy

# Clear all cached repos
python -m harness.runner --cache-clear

# Disable caching for a run
python -m harness.runner --tier tier4_swe --no-cache
```

**Benefits:**
- First run: Normal clone time (~2-5 min for large repos)
- Subsequent runs: ~5 seconds (worktree creation only)
- Shared across control/treatment groups
- Automatic fetch to update cached repos

---

### Phase 2: Docker Integration (Medium Effort) ✅ IMPLEMENTED

**Effort:** Medium (3-5 days)
**Impact:** Reproducible execution, dependency isolation

**Approach:** Use SWE-bench's official Docker harness

**Implementation (harness/docker_runner.py):**
- `check_docker_available()`: Check Docker daemon status
- `check_swebench_available()`: Check swebench package installation
- `extract_patch_from_workspace()`: Extract git diff after Claude's changes
- `create_predictions_file()`: Create swebench-compatible predictions JSONL
- `run_docker_evaluation()`: Run swebench harness evaluation
- `run_swe_task_with_docker()`: High-level Docker evaluation wrapper

**CLI Options:**
```bash
# Check Docker/swebench availability
python -m harness.runner --check-docker

# Run with Docker evaluation
python -m harness.runner --tier tier4_swe --docker

# Set Docker timeout
python -m harness.runner --tier tier4_swe --docker --docker-timeout 3600
```

**Original Design:**

```python
# harness/config.py
@dataclass
class BenchmarkConfig:
    # Existing fields...

    # Docker settings
    use_docker: bool = False
    docker_image_cache: Path = field(default_factory=lambda: Path.home() / ".cache/swe-bench/images")
    docker_timeout: int = 1800  # 30 minutes per task
```

**Implementation:**
```python
def run_swe_task_docker(task, workspace):
    """Run SWE task in Docker container."""

    # Use swebench's run_instance API
    from swebench.harness.run_evaluation import run_instance

    result = run_instance(
        instance=task.swe_metadata.to_swebench_format(),
        model_patch=workspace / "model_patch.diff",
        timeout=1800,
    )

    return {
        "resolved": result.resolved,
        "tests_passed": result.test_results.passed,
        "tests_failed": result.test_results.failed,
    }
```

**Docker Image Layers:**
```
┌─────────────────────────────────────┐
│  Instance Layer (task-specific)     │ ← Built per task
├─────────────────────────────────────┤
│  Environment Layer (Python env)     │ ← ~60 cached images
├─────────────────────────────────────┤
│  Base Layer (OS + common deps)      │ ← Shared
└─────────────────────────────────────┘
```

**Resource Requirements:**
- 8+ CPU cores
- 16GB+ RAM
- 120GB+ disk space

---

### Phase 3: Hybrid Mode (Recommended) ✅ IMPLEMENTED

**Approach:** Cache + optional Docker - best of both worlds

**Modes:**
| Mode | Cache | Docker | Use Case |
|------|-------|--------|----------|
| Fast (default) | ✅ | ❌ | Development, quick iteration |
| Reproducible | ✅ | ✅ | CI/CD, benchmarking |
| No-cache | ❌ | ❌ | Debug, fresh clone |

**CLI Examples:**
```bash
# Fast mode: cached repos, host execution (development)
python -m harness.runner --tier tier4_swe

# Reproducible mode: cache + Docker isolation (CI/benchmarking)
python -m harness.runner --tier tier4_swe --docker

# No-cache mode: fresh clone each time (debugging)
python -m harness.runner --tier tier4_swe --no-cache

# Full isolation: no cache + Docker (maximum reproducibility)
python -m harness.runner --tier tier4_swe --no-cache --docker
```

**Original Design:**

```python
def setup_swe_workspace(config, task_id, swe_metadata):
    if config.use_docker:
        return setup_docker_workspace(config, task_id, swe_metadata)
    else:
        return setup_cached_workspace(config, task_id, swe_metadata)
```

**Old CLI:**
```bash
# Fast mode: cached repos, host execution (development)
python -m harness.runner --tier tier4_swe --mode interactive

# Reproducible mode: Docker isolation (CI/benchmarking)
python -m harness.runner --tier tier4_swe --mode interactive --docker
```

---

## Implementation Plan

### Phase 1: Repository Caching (Week 1)

| Task | Effort | Priority |
|------|--------|----------|
| Add `cache_dir` to BenchmarkConfig | 1h | High |
| Implement `setup_cached_workspace()` | 4h | High |
| Add cache management (cleanup, stats) | 2h | Medium |
| Update documentation | 1h | Medium |

### Phase 2: Docker Integration (Week 2-3)

| Task | Effort | Priority |
|------|--------|----------|
| Add swebench to dependencies | 1h | High |
| Implement `run_swe_task_docker()` | 8h | High |
| Add `--docker` CLI flag | 2h | High |
| Handle Docker image caching | 4h | Medium |
| Add progress reporting for Docker builds | 2h | Low |

### Phase 3: Testing & Documentation (Week 3)

| Task | Effort | Priority |
|------|--------|----------|
| Test with 5+ real SWE-bench tasks | 4h | High |
| Benchmark: cache vs no-cache | 2h | High |
| Benchmark: Docker vs host | 2h | High |
| Update CHANGELOG | 1h | Medium |

---

## Expected Results

### Time Comparison

| Scenario | Current | With Cache | With Docker |
|----------|---------|------------|-------------|
| First run (astropy) | ~8 min | ~8 min | ~10 min |
| Repeat run | ~8 min | ~5 sec | ~2 min |
| Different commit | ~8 min | ~30 sec | ~3 min |

### Success Rate Comparison

| Scenario | Current | With Docker |
|----------|---------|-------------|
| Test execution | ~30% | ~95% |
| Reproducibility | Low | High |
| Cross-platform | Poor | Good |

---

## Decision Points

1. **Cache location:** `~/.cache/invar-benchmark/` vs project-local?
2. **Docker requirement:** Optional or required for SWE tasks?
3. **swebench dependency:** Add to core or optional `[swe]` group?

## References

- [SWE-bench Docker Setup](https://www.swebench.com/SWE-bench/guides/docker_setup/)
- [SWE-bench GitHub](https://github.com/princeton-nlp/SWE-bench)
- [swebench PyPI](https://pypi.org/project/swebench/)
