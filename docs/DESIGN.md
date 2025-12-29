# Invar Benchmark Framework Design

## Overview

This benchmark framework measures the effectiveness of the Invar framework when used with Claude Code through A/B testing.

- **Control Group**: Claude Code without Invar configuration
- **Treatment Group**: Claude Code with full Invar configuration (CLAUDE.md, INVAR.md, contracts, MCP tools)

## Architecture

```
invar-benchmark/
├── harness/                 # Benchmark execution engine
│   ├── runner.py           # Main benchmark runner
│   ├── config.py           # Configuration management
│   ├── collector.py        # Metrics collection
│   ├── display.py          # Rich progress visualization
│   └── models.py           # Data models (Task, Result, etc.)
├── eval/                    # Analysis and reporting
│   ├── analysis.py         # Statistical analysis (t-test, effect size)
│   └── report.py           # Report generation
├── tasks/                   # Task definitions (JSON)
│   ├── tier1_standard/     # Baseline tasks
│   ├── tier2_contracts/    # Contract-focused tasks
│   └── tier3_integration/  # Complex integration tasks
├── configs/                 # Group-specific configurations
│   ├── control/            # Empty CLAUDE.md
│   └── treatment/          # Full Invar configuration
├── workspace/              # Task execution directories
└── results/                # Experiment results
```

## Task Tiers

### Tier 1: Standard (7 tasks)
Baseline programming tasks to verify Invar doesn't add overhead.

| Task ID | Name | Source | Purpose |
|---------|------|--------|---------|
| task_001 | Calculate Average | Custom | Basic function |
| task_002 | Parse Key-Value Config | Custom | String parsing |
| task_003 | Two Fer | Exercism | Default parameters |
| task_004 | Raindrops | Exercism | Factor logic |
| task_005 | Hamming Distance | Exercism | String comparison |
| task_006 | Isogram | Exercism | Set operations |
| task_007 | Pangram | Exercism | Alphabet check |

### Tier 2: Contracts (8 tasks)
Tasks where contracts (@pre/@post) provide significant value.

| Task ID | Name | Contract Focus |
|---------|------|----------------|
| task_101 | Range Validator | @pre/@post decorators |
| task_102 | Safe Division | Result[T, E] error handling |
| task_103 | Order State Machine | State transition invariants |
| task_104 | Bank Account | Balance >= 0 invariant |
| task_105 | Date Range | start <= end invariant |
| task_106 | Pagination | Parameter bounds (1-100) |
| task_107 | Password Validator | Multi-rule validation |
| task_108 | Shopping Cart | Quantity/price constraints |

### Tier 3: Integration (5 tasks)
Complex multi-component tasks showcasing Result types and error propagation.

| Task ID | Name | Complexity Focus |
|---------|------|------------------|
| task_201 | Data Pipeline | Result.bind() chaining |
| task_202 | Retry Client | Exponential backoff + contracts |
| task_203 | Composable Validator | Error accumulation |
| task_204 | Task Scheduler | DAG + topological sort |
| task_205 | Config Manager | Layered priority + coercion |

## Metrics Collected

### Execution Metrics
- `iterations`: Tool calls / message exchanges
- `total_tokens`: Token count (tiktoken cl100k_base, with chars/4 fallback)
- `execution_time_seconds`: Wall clock time

### Quality Metrics
- `tests_passed` / `tests_total`: Visible test results
- `hidden_tests_passed` / `hidden_tests_total`: Edge case coverage
- `lines_of_code`: Non-comment, non-blank lines
- `cyclomatic_complexity`: Decision point density

### Invar-Specific (Treatment only)
- `has_contracts`: Whether @pre/@post decorators used
- `contract_coverage`: Contracts / (functions × 2)
- `guard_errors` / `guard_warnings`: Invar guard output

## Key Design Decisions

### 1. MCP Isolation via CLI Flags
**Problem**: Using `CLAUDE_CONFIG_DIR` to isolate MCP config also removed API authentication.

**Solution**: Use `--strict-mcp-config` and `--mcp-config` CLI flags instead:
```python
# Control: Block all MCP servers
cmd.extend(["--strict-mcp-config", "--mcp-config", '{"mcpServers": {}}'])

# Treatment: Add Invar MCP if available (tries uvx first, then invar command)
cmd.extend(["--mcp-config", json.dumps(mcp_config)])
```

### 2. Treatment Configuration
The treatment group includes full Invar configuration:

```
configs/treatment/
├── CLAUDE.md              # v5.0 - USBV workflow, skills, routing
├── INVAR.md               # Protocol reference
└── .invar/
    ├── context.md         # Task context (populated by harness)
    └── examples/
        ├── contracts.py   # @pre/@post patterns
        ├── core_shell.py  # Core/Shell separation
        └── workflow.md    # Visible workflow example
```

MCP server configuration (priority order):
```python
# Option 1: uvx (recommended - isolated, always up-to-date)
{"mcpServers": {"invar": {"command": "uvx", "args": ["invar-tools", "mcp"]}}}

# Option 2: local installation
{"mcpServers": {"invar": {"command": "python", "args": ["-m", "invar.mcp"]}}}
```

Fallback: Config files only (CLAUDE.md/INVAR.md) if MCP unavailable.

**Skill Embedding:** Since Skills cannot be auto-invoked in `--print` mode,
treatment prompts include USBV workflow guidance directly:
```python
if group == ExperimentGroup.TREATMENT:
    full_prompt = USBV_SKILL_PREFIX + task.prompt
```

### 3. Treatment Validation Results

Tested with `--print` mode:

| Component | Status | Notes |
|-----------|--------|-------|
| @pre/@post contracts | ✅ | Agent uses contracts correctly |
| Doctests | ✅ | Examples included in generated code |
| Core/Shell structure | ✅ | Files placed in correct directories |
| MCP Server | ✅ | `python -m invar.mcp` starts correctly |
| Check-In/Final | ⚠️ | May require interactive mode for display |

**Key Finding:** Core Invar functionality works in `--print` mode. The CLAUDE.md
guidance effectively directs the agent to use contracts and proper architecture.

### 4. AST-Based Contract Detection
**Problem**: Regex-based detection missed edge cases like `@deal.pre()`.

**Solution**: Use Python AST to parse decorators:
```python
contract_names = {"pre", "post", "require", "ensure", "invariant"}
for decorator in node.decorator_list:
    # Handle @pre(...), @deal.pre(...), etc.
```

### 5. Statistical Robustness
**Problem**: Zero-variance cases (all identical values) caused division by zero.

**Solution**: Added warnings and special handling in Welch's t-test:
```python
if var1 == 0 and var2 == 0:
    warning = "Zero variance in both groups"
    return (0.0, 1.0, warning) if mean1 == mean2 else (float("inf"), 0.0, warning)
```

### 6. Progress Visualization
**Solution**: Rich library for real-time progress:
- Progress bar with ETA
- Task status table (pending/running/completed)
- Running summary with pass rates
- Final comparison table with delta percentages

## Running Benchmarks

### Basic Usage
```bash
cd ~/Projects/invar-benchmark
source .venv/bin/activate

# Dry run to list tasks
python -m harness.runner --dry-run

# Run all tasks
python -m harness.runner

# Run specific tier
python -m harness.runner --tier tier2_contracts

# Run single task
python -m harness.runner --task task_101_range_validator

# Disable Rich progress (CI mode)
python -m harness.runner --no-progress
```

### Execution Modes (BM-02)

Two execution modes are supported:

**Print Mode (default):**
```bash
python -m harness.runner --mode print
```
- Single-shot execution with `--print` flag
- Faster, more deterministic
- No multi-turn agent behavior

**Interactive Mode:**
```bash
python -m harness.runner --mode interactive --max-turns 50 --interactive-timeout 120
```
- PTY-based execution simulating real terminal
- Agent can make multi-turn decisions
- Skill invocation enabled
- Auto-responds to Y/N prompts

| Feature | Print | Interactive |
|---------|-------|-------------|
| Multi-turn | ❌ | ✅ |
| Skill tool | ❌ | ✅ |
| Error recovery | ❌ | ✅ |
| Speed | Fast | Slower |
| Determinism | High | Lower |

### Output
Results are saved to `results/exp_YYYYMMDD_HHMMSS/`:
- `summary.json`: Aggregated statistics
- `results.json`: Detailed per-task results

## Statistical Analysis

### Welch's t-test
Used for comparing means between groups (handles unequal variances).

### Cohen's d Effect Size
- |d| < 0.2: Negligible
- 0.2 ≤ |d| < 0.5: Small
- 0.5 ≤ |d| < 0.8: Medium
- |d| ≥ 0.8: Large

### Key Hypotheses

| Metric | Expected Direction | Rationale |
|--------|-------------------|-----------|
| Hidden Test Pass Rate | Treatment > Control | Contracts catch edge cases |
| Iterations | Treatment ≤ Control | Guard catches errors early |
| Tokens | Treatment ≥ Control | Reading CLAUDE.md/INVAR.md |

## Future Enhancements

1. **HTML Report Generation**: Interactive charts with Plotly
2. **Parallel Execution**: Run tasks concurrently
3. **Regression Detection**: Compare across experiment runs
4. **Task Difficulty Calibration**: Adjust based on pilot results
