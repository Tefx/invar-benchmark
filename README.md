# Invar Benchmark

A benchmark framework for testing the effectiveness of the [Invar](https://github.com/tefx/Invar) framework with Claude Code.

## Status

| Component | Count | Status |
|-----------|-------|--------|
| Tier 1 Tasks | 115 | Ready |
| Tier 2 Tasks | 28 | Ready |
| Tier 3 Tasks | 5 | Ready |
| Tier 4 SWE Tasks | 7 | Ready |
| **Total** | **155** | **Validated** |

## Overview

This benchmark compares code quality between:
- **Control Group**: Claude Code without Invar configuration
- **Treatment Group**: Claude Code with full Invar configuration (CLAUDE.md, INVAR.md, contracts)

## Quick Start

```bash
# Create virtual environment
cd ~/Projects/invar-benchmark
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# List available tasks
python -m harness.runner --dry-run

# Run full benchmark
python -m harness.runner
```

## Command Reference

### Basic Commands

```bash
# List all tasks
python -m harness.runner --dry-run

# Run full benchmark (both groups, all tasks)
python -m harness.runner

# Run specific group
python -m harness.runner --group control
python -m harness.runner --group treatment

# Run specific tier
python -m harness.runner --tier tier1_standard
python -m harness.runner --tier tier2_contracts
python -m harness.runner --tier tier3_integration
python -m harness.runner --tier tier4_swe

# Run multiple tiers
python -m harness.runner --tier tier1_standard --tier tier2_contracts

# Run specific task
python -m harness.runner --task task_001_average
```

### Model Selection

```bash
# Use Claude Sonnet (default)
python -m harness.runner --model sonnet

# Use Claude Opus for complex tasks
python -m harness.runner --model opus --tier tier3_integration

# Use Claude Haiku for fast/cheap runs
python -m harness.runner --model haiku --tier tier1_standard
```

### Execution Modes

```bash
# Print mode (default, single-shot)
python -m harness.runner --mode print

# Interactive mode (PTY-based, multi-turn with auto-continuation)
python -m harness.runner --mode interactive

# Interactive with custom settings
python -m harness.runner --mode interactive --max-turns 100 --interactive-timeout 900
```

**Interactive Mode Features:**
- LLM-based semantic detection (requires OpenAI API key)
- Pattern-based fallback detection (cursor + waiting phrases)
- Auto-responds to Y/N prompts and continuation requests
- 60s idle fallback for edge cases

### Parallel Execution

```bash
# Run 2 tasks in parallel (default: sequential)
python -m harness.runner --parallel 2

# Run tier1-3 with 4 parallel tasks (no Docker, lightweight)
python -m harness.runner --parallel 4 --tier tier1_standard

# Run SWE tasks with 2 parallel (Docker resource limit)
python -m harness.runner --parallel 2 --tier tier4_swe
```

**Recommended parallelism:**
| Tier | Parallel | Notes |
|------|----------|-------|
| tier1-3 | 2-4 | No Docker, API rate limit is main constraint |
| tier4_swe | 1-2 | Docker containers need ~4GB RAM each |

### SWE-bench Tasks

```bash
# List SWE tasks
python -m harness.runner --dry-run --tier tier4_swe

# Run SWE task (Docker enabled by default for Python compatibility)
python -m harness.runner --tier tier4_swe --task swe_astropy_astropy_6938

# Run without Docker (not recommended, may have Python version issues)
python -m harness.runner --tier tier4_swe --no-docker

# Check Docker/swebench availability
python -m harness.runner --check-docker

# Download more SWE-bench tasks
python scripts/convert_swe_bench.py --limit 50
python scripts/convert_swe_bench.py --repos django/django --limit 20
```

**Note:** Docker is enabled by default for SWE-bench tasks to ensure correct Python version compatibility.

### Repository Cache (SWE-bench)

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

### Output Options

```bash
# Disable Rich progress (for CI)
python -m harness.runner --no-progress

# Set timeout per task (seconds)
python -m harness.runner --timeout 300

# Docker evaluation timeout
python -m harness.runner --tier tier4_swe --docker --docker-timeout 3600
```

### Report Generation

```bash
# Generate report from results
python -m eval.report results/exp_YYYYMMDD_HHMMSS/
```

### Common Workflows

```bash
# Quick test: Run one task with Haiku
python -m harness.runner --task task_001_average --model haiku

# Full benchmark: All tiers with Sonnet
python -m harness.runner --model sonnet

# SWE evaluation: Docker + Opus
python -m harness.runner --tier tier4_swe --docker --model opus

# CI pipeline: No progress, print mode
python -m harness.runner --no-progress --mode print

# Development: Interactive mode with cache
python -m harness.runner --tier tier4_swe --mode interactive
```

## Progress Visualization

The runner displays real-time progress:

```
╭────────────────────────────── Invar Benchmark ───────────────────────────────╮
│   Running benchmark... ━━━━━━━━━━━━━━━━━━━━━━━━ 100% (40/40) 0:45:23 │ 0:00:00│
│ ✓ Complete                                                                   │
╰──────────────────────────────────────────────────────────────────────────────╯
┏━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ Task                    ┃       Control       ┃     Treatment      ┃  Tier   ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━┩
│ task_001_average        │    ✓ 100% (179t)    │    ✓ 100% (97t)    │  tier1  │
│ task_101_range_validator│    ✓ 80% (210t)     │   ✓ 100% (185t)    │  tier2  │
│ ...                     │         ...         │        ...         │   ...   │
└─────────────────────────┴─────────────────────┴────────────────────┴─────────┘
```

## Task Tiers

### Tier 1: Standard Tasks (115)
Baseline tasks to verify Invar doesn't add overhead.

**Custom Tasks (7):**
| Task | Description | Source |
|------|-------------|--------|
| task_001 | Calculate Average | Custom |
| task_002 | Parse Key-Value Config | Custom |
| task_003 | Two Fer | Exercism |
| task_004 | Raindrops | Exercism |
| task_005 | Hamming Distance | Exercism |
| task_006 | Isogram | Exercism |
| task_007 | Pangram | Exercism |

**Exercism Tasks (108):** Including accumulate, acronym, affine_cipher, anagram, armstrong_numbers, bob, crypto_square, diamond, etl, flatten_array, gigasecond, grains, hello_world, leap, nth_prime, reverse_string, rna_transcription, roman_numerals, say, scrabble_score, series, space_age, word_count, and 85 more.

### Tier 2: Contract-Focused Tasks (28)
Tasks where @pre/@post contracts provide value.

**Custom Tasks (8):**
| Task | Contract Focus |
|------|----------------|
| task_101 | Range validation with @pre/@post |
| task_102 | Safe division with Result[T, E] |
| task_103 | State machine invariants |
| task_104 | Bank account (balance >= 0) |
| task_105 | Date range (start <= end) |
| task_106 | Pagination bounds |
| task_107 | Password validation rules |
| task_108 | Shopping cart constraints |

**Exercism Tasks (20):** Including bank_account, binary_search, binary_search_tree, bowling, circular_buffer, clock, complex_numbers, custom_set, grade_school, isbn_verifier, linked_list, luhn, matrix, phone_number, pythagorean_triplet, rational_numbers, robot_simulator, simple_linked_list, triangle, and kindergarten_garden.

### Tier 3: Integration Tasks (5)
Complex multi-component tasks with Result types.

| Task | Complexity Focus |
|------|------------------|
| task_201 | Data pipeline with Result chaining |
| task_202 | Retry client with exponential backoff |
| task_203 | Composable validator with error accumulation |
| task_204 | Task scheduler with DAG dependencies |
| task_205 | Layered configuration manager |

### Tier 4: SWE-bench Tasks (7)
Real-world bug fixes from open source projects.

| Task | Repository | Description |
|------|------------|-------------|
| swe_astropy_astropy_6938 | astropy/astropy | Real SWE-bench task |
| swe_astropy_astropy_12907 | astropy/astropy | Real SWE-bench task |
| swe_astropy_astropy_14182 | astropy/astropy | Real SWE-bench task |
| swe_astropy_astropy_14365 | astropy/astropy | Real SWE-bench task |
| swe_astropy_astropy_14995 | astropy/astropy | Real SWE-bench task |
| swe_sample_simple_bug | sample/calculator | Sample task (local) |
| + 1 more | Various | Additional SWE-bench tasks |

**SWE-bench Dataset:**
- Full: 2,294 tasks
- Verified: 500 tasks
- Lite: 300 tasks (12 repos)

## Metrics Collected

| Category | Metric | Description |
|----------|--------|-------------|
| **Correctness** | Test Pass Rate | Visible tests |
| | Hidden Test Pass Rate | Hidden edge case tests |
| **Efficiency** | Iterations | Number of tool calls |
| | Token Usage | Input/output tokens (from JSONL logs) |
| | Total Turns | Conversation turn count |
| **Quality** | Lines of Code | Generated code size |
| | Complexity | Cyclomatic complexity |
| **Invar-Specific** | Contract Coverage | % functions with @pre/@post |
| | Guard Results | Static analysis errors/warnings |
| | Check-In Rate | Protocol compliance (✓ Check-In marker) |
| | Final Rate | Protocol completion (✓ Final marker) |
| | Skill Calls | Number of Skill tool invocations |

## Directory Structure

```
invar-benchmark/
├── harness/                    # Benchmark execution
│   ├── runner.py              # Main runner with Rich display
│   ├── config.py              # Configuration management
│   ├── collector.py           # Metrics collection (AST-based)
│   ├── conversation_parser.py # JSONL conversation log parser
│   ├── display.py             # Progress visualization
│   ├── models.py              # Data models
│   ├── llm_detector.py        # LLM-based input detection
│   └── docker_runner.py       # Docker evaluation for SWE tasks
├── eval/                       # Analysis
│   ├── analysis.py            # Welch's t-test, Cohen's d
│   └── report.py              # Report generation
├── scripts/                    # Utility scripts
│   ├── convert_swe_bench.py   # Download/convert SWE-bench tasks
│   └── convert_exercism.py    # Download/convert Exercism tasks
├── tasks/                      # Task definitions (JSON)
│   ├── tier1_standard/        # 115 baseline tasks (7 custom + 108 Exercism)
│   ├── tier2_contracts/       # 28 contract tasks (8 custom + 20 Exercism)
│   ├── tier3_integration/     # 5 integration tasks
│   └── tier4_swe/             # 7 SWE-bench tasks
├── configs/                    # Group configurations
│   ├── control/               # Empty config
│   └── treatment/             # Full Invar config
├── docs/                       # Documentation
│   ├── DESIGN.md              # Architecture & decisions
│   └── CHANGELOG.md           # Development history
├── workspace/                  # Task execution (auto-created)
└── results/                    # Experiment results
```

## Configuration Isolation

MCP servers are isolated via CLI flags (preserves authentication):

```python
# Control: Block all MCP servers
cmd.extend(["--strict-mcp-config", "--mcp-config", '{"mcpServers": {}}'])

# Treatment: Add Invar MCP via python -m invar.mcp
cmd.extend(["--mcp-config", json.dumps({"mcpServers": {"invar": {...}}})])
```

## Treatment Environment

The treatment group includes full Invar v5.0 configuration:

| Component | Status | Description |
|-----------|--------|-------------|
| CLAUDE.md | ✅ | USBV workflow, skills, routing |
| INVAR.md | ✅ | Protocol v5.0 reference |
| .invar/examples/ | ✅ | Contract and Core/Shell patterns |
| MCP Server | ✅ | `python -m invar.mcp` |
| invar-runtime | ✅ | @pre/@post contract decorators |

**Validated:** Agent uses @pre/@post contracts and follows Core/Shell architecture.

## Adding Tasks

Create a JSON file in the appropriate tier directory:

```json
{
  "id": "task_XXX_name",
  "name": "Human Readable Name",
  "description": "What this task tests",
  "tier": "tier1_standard|tier2_contracts|tier3_integration",
  "prompt": "The task prompt for Claude Code...",
  "initial_files": {},
  "test_file": "# pytest tests (visible to Claude)...",
  "hidden_test_file": "# hidden tests (for evaluation only)...",
  "expected_files": ["src/core/solution.py"],
  "tags": ["tag1", "tag2"],
  "difficulty": "easy|medium|hard"
}
```

## Requirements

- Python 3.11+
- Claude Code CLI installed and authenticated
- Virtual environment (recommended)
- Docker (required for SWE-bench tasks)

### Core Dependencies

```bash
pip install -e ".[dev]"
```

### LLM Detection (Optional, for Interactive Mode)

For improved interactive mode automation, configure OpenAI API:

```bash
# Create .env file with API key
echo "OPENAI_API_KEY=sk-..." > .env

# Install openai package
pip install openai
```

The LLM detector uses GPT-4o-mini for cost-efficient semantic detection of agent waiting states. Falls back to pattern-based detection if unavailable.

### Treatment Group Dependencies

```bash
pip install invar-runtime deal returns
# Or install from local Invar project for full MCP support:
pip install -e /path/to/Invar
```

### SWE-bench Dependencies (Optional)

```bash
# For Docker-based evaluation
pip install -e ".[docker]"

# Requires Docker runtime (Docker Desktop, Colima, OrbStack, etc.)
# Check availability:
python -m harness.runner --check-docker
```

## Documentation

- [DESIGN.md](docs/DESIGN.md) - Architecture and design decisions
- [CHANGELOG.md](docs/CHANGELOG.md) - Development history

## License

MIT
