# BM-01: SWE-Bench Integration Proposal

## Status: Implemented ✅

## Problem

当前 benchmark 仅包含自定义任务，缺少业界标准的软件工程评测任务。
SWE-bench 是评估 LLM 解决真实 GitHub issue 能力的标准 benchmark。

## SWE-Bench 概述

| 特性 | SWE-bench | SWE-bench Lite |
|------|-----------|----------------|
| 任务数量 | 2,294 | 300 |
| 来源 | 12 个 Python 仓库 | 同上 (精选) |
| 任务类型 | Bug fix, feature | 同上 |
| 平均难度 | 中-高 | 中 |
| 评估方式 | Patch 正确性 | 同上 |

## 集成方案

### 方案 A: 直接集成 SWE-bench Lite

```
tasks/
├── tier4_swe/           # 新增 tier
│   ├── django__django-11099.json
│   ├── requests__requests-2674.json
│   └── ...
```

**任务格式适配:**
```json
{
  "id": "swe_django_11099",
  "name": "Django #11099",
  "description": "Fix: Model.full_clean() should not validate...",
  "tier": "tier4_swe",
  "prompt": "Fix the issue described below...\n\n{issue_text}",
  "initial_files": {
    "setup": "git clone --branch {base_commit} {repo}"
  },
  "test_file": "{test_patch}",
  "hidden_test_file": "{test_patch}",
  "expected_files": [],
  "swe_metadata": {
    "repo": "django/django",
    "base_commit": "abc123",
    "issue_url": "https://github.com/django/django/issues/11099",
    "gold_patch": "..."
  }
}
```

**评估方式:**
1. 应用生成的 patch
2. 运行原始测试 (`{test_patch}`)
3. 比较通过率

### 方案 B: SWE-style 自定义任务

不使用真实 SWE-bench，而是创建类似风格的任务：

```
tasks/
├── tier4_debugging/     # 调试类任务
│   ├── task_401_fix_edge_case.json
│   ├── task_402_resolve_race_condition.json
│   └── ...
```

**特点:**
- 提供有 bug 的初始代码
- 描述 bug 现象（模拟 issue）
- 测试覆盖 bug 场景
- 评估修复正确性

### 方案 C: 混合方案

1. **Tier 4 (SWE-Lite):** 选择 20-30 个难度适中的 SWE-bench Lite 任务
2. **Tier 5 (SWE-Custom):** 自定义调试任务，专注 Invar 场景

## 技术挑战

### 1. 仓库设置

SWE-bench 任务需要完整仓库环境：

```python
def setup_swe_workspace(task: Task, workspace: Path) -> None:
    """Set up SWE-bench task workspace."""
    meta = task.swe_metadata

    # Clone at specific commit
    subprocess.run([
        "git", "clone", "--depth", "1",
        "--branch", meta["base_commit"],
        f"https://github.com/{meta['repo']}.git",
        str(workspace)
    ])

    # Install dependencies
    subprocess.run(["pip", "install", "-e", "."], cwd=workspace)
```

### 2. 评估方式差异

| 当前评估 | SWE-bench 评估 |
|----------|----------------|
| 测试通过率 | Patch 正确性 |
| 代码质量指标 | 回归测试通过 |
| 合约覆盖率 | N/A (现有代码) |

**适配方案:**
```python
def evaluate_swe_task(workspace: Path, task: Task) -> dict:
    """Evaluate SWE-bench task result."""
    # Get generated patch
    result = subprocess.run(
        ["git", "diff", task.swe_metadata["base_commit"]],
        cwd=workspace, capture_output=True, text=True
    )
    generated_patch = result.stdout

    # Run test suite
    test_result = subprocess.run(
        ["pytest", "-x", task.swe_metadata["test_path"]],
        cwd=workspace, capture_output=True
    )

    return {
        "patch_generated": bool(generated_patch),
        "tests_passed": test_result.returncode == 0,
        "patch_similarity": compute_patch_similarity(
            generated_patch,
            task.swe_metadata["gold_patch"]
        )
    }
```

### 3. Invar 集成问题

SWE-bench 仓库通常没有 Invar 配置：
- 无 `@pre/@post` 合约
- 无 Core/Shell 架构
- 无 CLAUDE.md/INVAR.md

**处理方案:**
- Treatment 组仍注入 USBV 工作流指导
- 评估时不检查合约覆盖率
- 新增指标：是否添加了合约到修复代码

## 实施计划

### Phase 1: 可行性验证 (1 周)
1. 下载 SWE-bench Lite 数据集
2. 手动运行 3-5 个任务
3. 验证评估流程

### Phase 2: 任务适配 (2 周)
1. 选择 20 个适合的任务
2. 转换为 benchmark 格式
3. 实现 SWE 特定的 setup/evaluate

### Phase 3: 集成测试 (1 周)
1. 运行完整 benchmark
2. 验证结果可靠性
3. 文档化

## 预期结果

| 指标 | Control | Treatment (预期) |
|------|---------|-----------------|
| SWE 任务通过率 | ~15% | ~20% (+33%) |
| 首次尝试成功率 | ~10% | ~15% (+50%) |
| 回归测试保持率 | ~80% | ~85% (+6%) |

## 开放问题

1. SWE-bench 任务执行时间较长 (5-15 分钟/任务)，如何优化？
2. 是否需要 Docker 隔离？
3. 如何处理需要外部服务的任务 (数据库、Redis 等)？

## 参考

- [SWE-bench](https://github.com/princeton-nlp/SWE-bench)
- [SWE-bench Lite](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Lite)
- [SWE-agent](https://github.com/princeton-nlp/SWE-agent)
