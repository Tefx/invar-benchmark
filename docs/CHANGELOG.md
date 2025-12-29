# Invar Benchmark Development Changelog

## 2024-12-29

### Initial Framework Creation

**Created core benchmark infrastructure:**
- `harness/runner.py` - Main benchmark execution engine
- `harness/config.py` - Configuration and workspace management
- `harness/collector.py` - Metrics collection system
- `harness/models.py` - Data models (Task, TaskResult, ExperimentResult)
- `eval/analysis.py` - Statistical analysis (Welch's t-test, Cohen's d)
- `eval/report.py` - Report generation

**Initial task set (5 tasks):**
- Tier 1: task_001_average, task_002_parser
- Tier 2: task_101_range_validator, task_102_safe_division, task_103_state_machine

### Critical Fixes

#### CRIT-1: MCP Isolation Incomplete
- **Issue**: Control group could access global MCP servers
- **Fix**: Added `_setup_control_config()` with explicit empty MCP config

#### CRIT-2: Git Config Failure
- **Issue**: `git init` failed without user.name/email in CI
- **Fix**: Configure local git user in `setup_workspace()`

#### CRIT-3: API Authentication Lost
- **Issue**: `CLAUDE_CONFIG_DIR` isolation removed API auth
- **Fix**: Replaced with `--strict-mcp-config` and `--mcp-config` CLI flags

### Major Fixes

#### MAJ-1: Contract Detection Flawed
- **Issue**: Regex missed `@deal.pre()` style decorators
- **Fix**: Implemented AST-based `_count_contracts_ast()` method

#### MAJ-2: Division by Zero in Statistics
- **Issue**: Zero variance caused crash in t-test
- **Fix**: Added warning field and special handling in `welch_t_test()`

#### MAJ-3: Execution Time Not Set
- **Issue**: `execution_time_seconds` never calculated
- **Fix**: Added calculation after task completion

#### MAJ-4: Token Estimation Unreliable
- **Issue**: No API access for actual token counts
- **Fix**: Added documentation noting it's character-based proxy

#### MAJ-5: MCP Schema Error
- **Issue**: Empty `{}` doesn't match MCP config schema
- **Fix**: Changed to `{"mcpServers": {}}`

### Progress Visualization

**Added Rich-based progress display:**
- Created `harness/display.py` with `ProgressDisplay` class
- Real-time progress bar with ETA
- Task status table (pending/running/completed)
- Running summary panel
- Final comparison table with delta percentages

**CLI Options:**
- Default: Rich progress visualization
- `--no-progress`: Simple text output for CI

### Task Expansion

**Added Tier 1 tasks from Exercism (5 new):**
- task_003_two_fer - String formatting
- task_004_raindrops - Factor logic
- task_005_hamming - Hamming distance
- task_006_isogram - No repeating letters
- task_007_pangram - All alphabet letters

**Added Tier 2 custom contract tasks (5 new):**
- task_104_bank_account - Balance invariant
- task_105_date_range - start <= end invariant
- task_106_pagination - Parameter bounds
- task_107_password - Multi-rule validation
- task_108_shopping_cart - Quantity/price constraints

**Added Tier 3 integration tasks (5 new):**
- task_201_pipeline - Result-based data pipeline
- task_202_retry_client - Exponential backoff with contracts
- task_203_validator - Composable validation with error accumulation
- task_204_scheduler - Task DAG with dependencies
- task_205_config - Layered configuration manager

### Current Status

**Task Count:** 20 total
- Tier 1 (Standard): 7 tasks
- Tier 2 (Contracts): 8 tasks
- Tier 3 (Integration): 5 tasks

**Validated:** All tasks load correctly via `--dry-run`

**Pilot Tested:** task_001_average passes for both groups

### Treatment Configuration Update

**Updated treatment environment to match Invar v5.0:**
- CLAUDE.md updated with skills, commands, routing control (DX-42)
- INVAR.md synced with Protocol v5.0 (USBV workflow)
- Examples synced (contracts.py, core_shell.py, workflow.md)
- MCP server fixed to use `python -m invar.mcp`

**Configuration structure:**
```
configs/treatment/
├── CLAUDE.md              # v5.0 - USBV workflow, routing
├── INVAR.md               # Protocol reference
└── .invar/
    ├── context.md         # Task context template
    └── examples/          # Reference patterns
```

### Treatment Environment Validation

**Dependencies installed:**
- `invar-runtime` 1.3.0
- `invar-tools` 1.4.0 (local dev)
- `deal`, `returns` libraries

**MCP Server:**
- Command: `python -m invar.mcp`
- Status: ✅ Starts correctly

**Skill Test Results (--print mode):**
| Check | Result | Notes |
|-------|--------|-------|
| @pre/@post contracts | ✅ | Agent uses contracts correctly |
| Doctests | ✅ | Examples included |
| Core/Shell structure | ✅ | Files in correct locations |
| Check-In display | ❌ | May require interactive mode |
| Routing announcement | ❌ | May require interactive mode |

**Conclusion:** Core Invar functionality (contracts, architecture) works in --print mode.
Full skill routing requires interactive mode.

### Skill Embedding Solution

**Problem:** Skills cannot be auto-invoked in `--print` mode (no Skill tool).

**Solution:** Embed USBV skill guidance directly in treatment prompts:
```python
USBV_SKILL_PREFIX = """# Development Instructions (USBV Workflow)
Follow this workflow:
1. UNDERSTAND: Check existing code structure
2. SPECIFY: Write @pre/@post contracts BEFORE implementation
3. BUILD: Implement following the contracts
4. VALIDATE: Run invar guard to verify
...
"""

# Treatment group gets skill prefix
if group == ExperimentGroup.TREATMENT:
    full_prompt = USBV_SKILL_PREFIX + task.prompt
```

**MCP Server:** Updated to use `uvx invar-tools mcp` (PyPI now has mcp command).

### BM-02 Feasibility Verification ✅

**Objective:** Test if interactive mode (without --print) can work for benchmarking.

**Test Results:**

| Test | Method | Result | Notes |
|------|--------|--------|-------|
| Simple subprocess | `subprocess.run()` | ❌ Timeout | Blocks without TTY |
| PTY + simple task | `pty.openpty()` | ✅ Pass | "Hello World" output |
| PTY + file creation | PTY + Popen | ✅ Pass | Created math.py |
| PTY + treatment config | PTY + CLAUDE.md | ✅ Pass | Uses `@deal.pre/post` |

**Key Findings:**
1. PTY simulation is **required** - pure subprocess times out
2. `--dangerously-skip-permissions` enables autonomous execution
3. Agent completes tasks and exits automatically
4. Treatment config (CLAUDE.md) guidance is effective
5. Contracts are used with `deal` library syntax

**Status:** Phase 1 (feasibility) complete. Ready for Phase 2 (integration).

### Token Counting Improved with Tiktoken

**Problem:** MAJ-4 noted token estimation was unreliable (chars/4 approximation).

**Solution:** Integrated tiktoken library for accurate token counting.

```python
# harness/collector.py
from harness.collector import count_tokens

tokens, is_accurate = count_tokens(text)
# is_accurate = True when tiktoken used
# is_accurate = False when fallback to chars/4
```

**Comparison (task_001_average):**
| Method | Result |
|--------|--------|
| Old (chars/4) | 198 tokens |
| Tiktoken (cl100k_base) | 231 tokens |
| Difference | +16.7% |

**Changes:**
- `pyproject.toml`: Added `tiktoken>=0.5.0` dependency
- `harness/collector.py`: Added `count_tokens()` with graceful fallback

### BM-02 Implementation Complete ✅

**Implemented:**
- `harness/config.py`: Added `execution_mode`, `max_turns`, `interactive_timeout` config options
- `harness/runner.py`: Added `_run_interactive_pty()` PTY-based execution method
- CLI: Added `--mode`, `--max-turns`, `--interactive-timeout` parameters

**Usage:**
```bash
# Print mode (default, single-shot)
python -m harness.runner --mode print

# Interactive mode (PTY-based, multi-turn)
python -m harness.runner --mode interactive --max-turns 50 --interactive-timeout 120
```

**Validation Results (task_001_average):**
| Mode | Test Pass | Hidden Test | Tokens |
|------|-----------|-------------|--------|
| print | 100% | 100% | 201 |
| interactive | 100% | 100% | 128 |

### SWE-Bench Integration (BM-01)

**Implemented:**
- `harness/models.py`: Added `SWEMetadata` dataclass and `TIER4_SWE` tier
- `scripts/convert_swe_bench.py`: Script to download and convert SWE-bench Lite tasks
- `tasks/tier4_swe/`: Directory for SWE-bench tasks with sample task

**Usage:**
```bash
# Install SWE dependencies
pip install datasets gitpython

# Convert SWE-bench Lite tasks (limit to 10 for testing)
python scripts/convert_swe_bench.py --limit 10

# Convert specific repos
python scripts/convert_swe_bench.py --repos django/django,psf/requests --limit 5

# Run SWE tasks
python -m harness.runner --tier tier4_swe --mode interactive
```

**Task Format:**
```json
{
  "id": "swe_django_django_11099",
  "tier": "tier4_swe",
  "swe_metadata": {
    "instance_id": "django__django-11099",
    "repo": "django/django",
    "base_commit": "abc123...",
    "fail_to_pass": ["test_foo", "test_bar"],
    "pass_to_pass": ["test_existing"]
  }
}
```

## Proposals

| ID | Title | Status |
|----|-------|--------|
| [BM-01](proposals/BM-01-swe-bench-integration.md) | SWE-Bench Integration | **Implemented** |
| [BM-02](proposals/BM-02-interactive-mode-benchmark.md) | Interactive Mode Benchmark | **Implemented** |
| [BM-03](proposals/BM-03-swe-bench-improvements.md) | SWE-Bench Improvements | **Implemented** |

### SWE-Bench Workspace Setup

**Implemented:**
- `harness/config.py`: Added `setup_swe_workspace()` for cloning repositories
- `harness/collector.py`: Added `_run_swe_tests()` for SWE-specific test execution
- `harness/runner.py`: Detects SWE tasks and uses appropriate workspace/test setup

**Features:**
- Shallow clone with `--filter=blob:none` for speed
- Checkout at specific `base_commit`
- Auto-detect and install dependencies (`pip install -e .`)
- Separate handling for `fail_to_pass` (hidden tests) and `pass_to_pass` (regression tests)

**Usage:**
```bash
# Run sample SWE task (uses initial_files, no clone needed)
python -m harness.runner --tier tier4_swe --task swe_sample_simple_bug

# Run real SWE-bench task (clones astropy)
python -m harness.runner --tier tier4_swe --task swe_astropy_astropy_6938
```

**Known Limitations:**
- Large projects (astropy, django) require significant time for clone/install
- Some projects need additional system dependencies (C compilers, etc.)
- Docker isolation recommended for consistent environment (future work)

### BM-03 Phase 1: Repository Caching (Implemented)

**Added cache management for SWE-bench repositories:**
- `harness/config.py`: Added `_get_or_create_bare_repo()`, `_create_worktree()`, `get_cache_stats()`, `clear_cache()`
- `harness/runner.py`: Added `--cache-stats`, `--cache-clear`, `--no-cache` CLI options
- Cache location: `.cache/bare_repos/`

**Usage:**
```bash
# Show cache statistics
python -m harness.runner --cache-stats

# Clear specific repo cache
python -m harness.runner --cache-clear astropy/astropy

# Disable caching for a run
python -m harness.runner --tier tier4_swe --no-cache
```

**Performance:**
- First run: Normal clone time (~2-5 min)
- Subsequent runs: ~5 seconds (worktree creation only)

### BM-03 Phase 2: Docker Integration (Implemented)

**Added Docker-based SWE evaluation:**
- `harness/docker_runner.py`: New module for Docker evaluation
  - `check_docker_available()`: Check Docker daemon status
  - `check_swebench_available()`: Check swebench installation
  - `extract_patch_from_workspace()`: Extract git diff
  - `run_docker_evaluation()`: Run swebench in Docker
- `pyproject.toml`: Added `[docker]` optional dependency group

**CLI Options:**
```bash
# Check Docker availability
python -m harness.runner --check-docker

# Run with Docker evaluation
python -m harness.runner --tier tier4_swe --docker --docker-timeout 3600
```

### BM-03 Phase 3: Hybrid Mode (Implemented)

**Flexible mode combinations:**
| Mode | Command | Use Case |
|------|---------|----------|
| Fast | `--tier tier4_swe` | Development |
| Reproducible | `--tier tier4_swe --docker` | CI/Benchmarking |
| No-cache | `--tier tier4_swe --no-cache` | Debug |
| Full isolation | `--tier tier4_swe --no-cache --docker` | Maximum reproducibility |

### Lazy Import Fix

**Fixed ProgressDisplay import to be lazy:**
- `harness/runner.py`: Moved `ProgressDisplay` import inside `_run_with_rich_display()` method
- Allows `--check-docker`, `--cache-stats`, `--help` to work without `rich` installed
- Full benchmark execution still requires `rich` for progress visualization

### Model Selection

**Added Claude model selection feature:**
- `harness/config.py`: Added `claude_model` field (default: "sonnet")
- `harness/runner.py`: Added `--model` CLI flag with choices: opus, sonnet, haiku
- Model passed to Claude CLI via `--model` flag

**Usage:**
```bash
# Use Sonnet (default)
python -m harness.runner --tier tier1_standard

# Use Opus for more complex tasks
python -m harness.runner --tier tier3_integration --model opus

# Use Haiku for faster/cheaper runs
python -m harness.runner --tier tier1_standard --model haiku
```

## 2024-12-30

### BM-10: Conversation Message Preservation ✅

**Problem:** Check-In detection was unreliable; conversation messages were not preserved in results.

**Fixed:**
- `harness/conversation_parser.py`: Added `messages` field to `ConversationMetrics`
- Stricter Check-In pattern detection using regex (`✓ Check-In:` prefix required)
- Extract both user and assistant message content
- Populate messages from JSONL logs

**Detection Pattern:**
```python
# Old (too permissive): "Check-In:" anywhere in content
# New (strict): r"✓\s*Check-In:" at line start
```

### BM-09: Multiple Tier Selection ✅

**Added:** Support for running multiple tiers in single command.

```bash
# Run tier1 and tier2 together
python -m harness.runner --tier tier1_standard --tier tier2_contracts

# Run all non-SWE tiers
python -m harness.runner --tier tier1_standard --tier tier2_contracts --tier tier3_integration
```

### BM-08: Exercism Task Expansion ✅

**Added:** 128 Exercism tasks to benchmark dataset.

**Implementation:**
- `scripts/convert_exercism.py`: Script to convert Exercism Python track exercises
- Auto-categorization: Tier 1 (standard) vs Tier 2 (contracts) based on exercise characteristics
- Fix: Remove `self` parameter from converted test functions

**Task Distribution:**
| Tier | Count | Source |
|------|-------|--------|
| Tier 1 (Standard) | 108 | Exercism (simple exercises) |
| Tier 2 (Contracts) | 20 | Exercism (stateful/validation exercises) |
| **Total New** | **128** | |

### BM-07: Skill Tool Invocation (Reverted)

**Attempted:** Add system prompt to enforce Skill tool invocation.

**Result:** Reverted - approach was not effective. Solution moved to DX-67 (explicit Skill tool syntax in routing table).

### BM-06: Conversation Log Parsing Robustness ✅

**Fixed:** Improved JSONL parsing to handle edge cases:
- Empty lines in log files
- Malformed JSON entries
- Missing fields graceful handling

### BM-05: Natural Routing Mode ✅

**Added:** Fair comparison mode that allows natural workflow routing.

**Changes:**
- Copy `.claude/skills/` to treatment workspace
- Enable Skill tool invocation for treatment group
- Fair A/B comparison without artificial restrictions

### BM-04: JSONL Conversation Parser ✅

**Added:** Accurate metrics extraction from Claude Code conversation logs.

**Implementation:**
- `harness/conversation_parser.py`: Parse `.claude/projects/<id>/conversations/<id>.jsonl`
- Extract: token usage, turn count, tool calls, protocol markers
- Track Check-In and Final markers for Invar protocol compliance

**Metrics Tracked:**
| Metric | Source | Description |
|--------|--------|-------------|
| `input_tokens` | JSONL | Total input tokens |
| `output_tokens` | JSONL | Total output tokens |
| `total_turns` | JSONL | Conversation turns |
| `checkin_rate` | Pattern | Check-In protocol compliance |
| `final_rate` | Pattern | Final marker compliance |

### Earlier Changes (Dec 29)

**Parallel Execution:**
- Added `--parallel N` flag for concurrent task execution
- Recommended: 2-4 for tier1-3, 1-2 for tier4_swe (Docker resource limit)

**LLM-based Detection:**
- Added semantic detection for agent waiting states (requires OpenAI API)
- Pattern-based fallback when LLM unavailable
- 60s idle timeout as final fallback

**Configuration Updates:**
- Timeout increased to 30 minutes (1800s)
- Max turns increased to 1000
- Docker enabled by default for SWE tasks

## Proposals

| ID | Title | Status |
|----|-------|--------|
| [BM-01](proposals/BM-01-swe-bench-integration.md) | SWE-Bench Integration | **Implemented** |
| [BM-02](proposals/BM-02-interactive-mode-benchmark.md) | Interactive Mode Benchmark | **Implemented** |
| [BM-03](proposals/BM-03-swe-bench-improvements.md) | SWE-Bench Improvements | **Implemented** |
| BM-04 | JSONL Conversation Parser | **Implemented** |
| BM-05 | Natural Routing Mode | **Implemented** |
| BM-06 | Parsing Robustness | **Implemented** |
| BM-07 | Skill Invocation Enforcement | **Reverted** |
| BM-08 | Exercism Task Expansion | **Implemented** |
| BM-09 | Multiple Tier Selection | **Implemented** |
| BM-10 | Message Preservation | **Implemented** |

## Pending Work

1. Run full benchmark suite (with interactive mode comparison)
2. Generate HTML reports with charts
3. ~~Add parallel execution support~~ ✅ Done
4. ~~Implement BM-01 (SWE-Bench integration)~~ ✅ Done (basic infrastructure)
5. ~~Implement BM-02 Phase 2 (PTY integration into runner.py)~~ ✅ Done
6. Create task difficulty calibration
7. ~~Add Docker isolation for SWE-bench tasks~~ ✅ Done (BM-03 Phase 2)
8. ~~Expand task dataset~~ ✅ Done (BM-08: 128 Exercism tasks)
