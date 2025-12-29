# BM-02: Interactive Mode Benchmark Proposal

## Status: Implemented ✅

## Problem

当前使用 `--print` 模式的限制：

| 限制 | 影响 |
|------|------|
| 单次 prompt | 无法迭代改进 |
| 无 Skill tool | Skills 无法自动调用 |
| 无自主决策 | Agent 不能主动验证/修复 |
| 无真实体验 | 不代表实际使用场景 |

## 为什么使用 --print 模式？

历史原因：
1. **简单可控** - 输入输出明确
2. **易于捕获** - stdout 直接获取结果
3. **无 stdin 处理** - 避免交互复杂性
4. **确定性** - 相同输入产生可比较的输出

## Interactive Mode 可行性分析

### Claude Code 支持的自动化选项

```bash
# 1. --dangerously-skip-permissions
#    跳过所有权限确认 (文件、命令等)

# 2. --allowedTools
#    预授权特定工具使用

# 3. 环境变量控制
#    CLAUDE_CODE_TIMEOUT, CLAUDE_CODE_MAX_TURNS 等
```

### 关键发现：Agent 可以自主决策

Claude Code agent 设计时就支持自主决策：
- 遇到错误会自动尝试修复
- 会主动运行测试验证
- 会调用 Skill tool 进入工作流

**问题在于：** 我们没有让它这样做。

## 方案：Autonomous Benchmark Mode

### 核心思路

让 agent 像真实用户交互一样工作，但自动化控制边界条件。

```python
def run_autonomous_task(task: Task, group: ExperimentGroup) -> TaskResult:
    """Run task in autonomous interactive mode."""

    # 构建命令 - 关键：不使用 --print
    cmd = [
        "claude",
        "--dangerously-skip-permissions",  # 自动授权
        "--max-turns", "50",               # 限制回合数
        "-p", task.prompt,                 # 初始 prompt
    ]

    # MCP 配置
    if group == ExperimentGroup.TREATMENT:
        cmd.extend(["--mcp-config", json.dumps(mcp_config)])

    # 使用 pexpect 或 subprocess 处理交互
    process = pexpect.spawn(" ".join(cmd), timeout=600)

    # 等待完成或超时
    try:
        process.expect(pexpect.EOF, timeout=600)
        output = process.before.decode()
    except pexpect.TIMEOUT:
        output = process.before.decode()
        process.terminate()

    return parse_result(output, task)
```

### 方案 A: 纯 subprocess (简单)

```python
import subprocess

def run_interactive_simple(task: Task) -> str:
    """Simple approach: let Claude run to completion."""
    result = subprocess.run(
        [
            "claude",
            "--dangerously-skip-permissions",
            "-p", task.prompt,
        ],
        capture_output=True,
        text=True,
        timeout=600,  # 10 分钟超时
        cwd=workspace,
    )
    return result.stdout
```

**问题：** Claude 可能会等待用户确认，导致卡住。

### 方案 B: PTY + 自动响应 (推荐)

```python
import pty
import os
import select

def run_interactive_pty(task: Task, workspace: Path) -> str:
    """Use PTY to handle interactive prompts."""

    master, slave = pty.openpty()

    process = subprocess.Popen(
        ["claude", "--dangerously-skip-permissions", "-p", task.prompt],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        cwd=workspace,
    )

    os.close(slave)
    output = []

    while True:
        ready, _, _ = select.select([master], [], [], 1.0)
        if ready:
            try:
                data = os.read(master, 1024).decode()
                output.append(data)

                # 检测需要响应的提示
                if "Continue? [Y/n]" in data or "[Y/N]" in data:
                    os.write(master, b"Y\n")  # 自动确认
                elif "Choose option" in data:
                    os.write(master, b"1\n")  # 选择第一项

            except OSError:
                break

        if process.poll() is not None:
            break

    return "".join(output)
```

### 方案 C: Claude Code SDK (最佳但需开发)

如果 Claude Code 提供 SDK：

```python
from claude_code import Session

async def run_with_sdk(task: Task) -> TaskResult:
    """Hypothetical SDK-based approach."""
    session = Session(
        auto_approve=True,
        max_turns=50,
        timeout=600,
    )

    await session.send(task.prompt)

    # 等待 agent 自行完成
    result = await session.wait_for_completion()

    return TaskResult(
        output=result.conversation,
        files=result.generated_files,
        tool_calls=result.tool_usage,
    )
```

## Interactive Mode 的优势

### 1. Skill 自动调用

```
User: "implement a calculator"

Agent (interactive mode):
📍 Routing: /develop — "implement" trigger detected
   Task: implement a calculator

✓ Check-In: project | main | clean

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📍 /develop → UNDERSTAND (1/4)
...
```

### 2. 自主错误修复

```
Agent: *writes code*
Agent: *runs invar guard*
Guard: ERROR: missing_contract on calculate()
Agent: *adds @pre/@post*
Agent: *runs invar guard again*
Guard: PASS
Agent: ✓ Final: guard PASS | 0 errors
```

### 3. 真实用户体验

评估的是实际使用场景，而非人工构造的单次交互。

## 技术挑战

### 1. 非确定性

Interactive mode 有更多随机性：
- Agent 决策路径不同
- 错误恢复策略不同
- 工具调用顺序不同

**缓解：** 多次运行取平均值

### 2. 执行时间

Interactive mode 通常更慢：
- 多轮对话
- 自我验证循环
- 工具调用延迟

**缓解：** 设置合理的 max_turns 和 timeout

### 3. 输出解析

Interactive mode 输出更复杂：
- 包含 ANSI 颜色码
- 进度指示器
- 多轮对话混合

**缓解：** 使用 `--output-format json` (如果支持)

## 可行性验证结果 (2024-12-29) ✅

### Phase 1 测试结果

**测试 1: 纯 subprocess (无 --print)**
```bash
claude --dangerously-skip-permissions -p "say hello world"
```
- 结果: ❌ 超时 - subprocess 在 TTY 环境外无法正常工作

**测试 2: PTY + 简单任务**
```python
# PTY 模拟终端环境
master, slave = pty.openpty()
process = subprocess.Popen(cmd, stdin=slave, stdout=slave, stderr=slave)
```
- 结果: ✅ 成功 - exit code 0, 输出 "Hello World"

**测试 3: PTY + 文件创建**
```
Prompt: "Create a file src/core/math.py with an add function"
```
- 结果: ✅ 成功 - 文件已创建，包含完整的 add() 函数

**测试 4: PTY + Treatment Config + Contracts**
```
Prompt: "Create calculate_average function with contracts"
```
- 结果: ✅ 成功 - 文件创建，使用 `@deal.pre/@deal.post` 合约
- 注意: 合约使用 `deal` 库语法 (`@deal.pre`), 非自定义 `@pre`

### 关键发现

| 测试项 | 结果 | 备注 |
|--------|------|------|
| PTY 模拟 | ✅ | 必须使用 PTY 而非纯 subprocess |
| 自动完成 | ✅ | Agent 完成任务后自动退出 |
| 文件创建 | ✅ | 无需用户确认 (--dangerously-skip-permissions) |
| Treatment 配置 | ✅ | CLAUDE.md 指导生效，使用合约 |
| 合约格式 | ⚠️ | 使用 `@deal.pre/post` 而非 `@pre/@post` |

### 验证代码

```python
def run_interactive_pty(prompt: str, workspace: Path, timeout: int = 120) -> tuple[int, str]:
    """Verified working implementation."""
    import pty
    import os
    import select

    master, slave = pty.openpty()
    cmd = ["claude", "--dangerously-skip-permissions", "-p", prompt]

    process = subprocess.Popen(
        cmd,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        cwd=workspace,
    )
    os.close(slave)

    output = []
    start_time = time.time()

    while True:
        if time.time() - start_time > timeout:
            process.terminate()
            break

        ready, _, _ = select.select([master], [], [], 1.0)
        if ready:
            try:
                data = os.read(master, 4096).decode("utf-8", errors="replace")
                output.append(data)
            except OSError:
                break

        if process.poll() is not None:
            break

    os.close(master)
    return process.returncode or 0, "".join(output)
```

### 结论

**Phase 1 完成: 可行性已验证。**

PTY 方案 (方案 B) 是可行的：
- Agent 可以自主完成任务
- 无需用户交互输入
- Treatment 配置 (CLAUDE.md) 生效
- 合约被正确使用

## 实施计划

### Phase 1: 可行性验证 ✅ COMPLETED

已完成验证，见上方结果。

### Phase 2: PTY 方案实现 ✅ COMPLETED

实现 `_run_interactive_pty()` 方法：
- 使用 `pty.openpty()` 创建伪终端
- 自动响应 Y/N 提示
- 完整输出捕获
- 超时处理 (可配置)

### Phase 3: 集成测试 ✅ COMPLETED

对比 --print vs interactive (task_001_average)：

| 指标 | Print Mode | Interactive Mode |
|------|------------|------------------|
| 任务完成率 | 100% | 100% |
| 测试通过率 | 100% | 100% |
| 隐藏测试通过率 | 100% | 100% |
| Token 使用 | 201 | 128 |

结论: 两种模式都能正确完成任务。

### Phase 4: 生产部署 ✅ COMPLETED

**已添加:**
- `harness/config.py`: `execution_mode`, `max_turns`, `interactive_timeout` 配置项
- `harness/runner.py`: `_run_interactive_pty()` 方法, 执行模式分发逻辑
- CLI 参数: `--mode`, `--max-turns`, `--interactive-timeout`

**使用方法:**
```bash
# Print 模式 (默认)
python -m harness.runner --mode print

# Interactive 模式
python -m harness.runner --mode interactive --max-turns 50 --interactive-timeout 120
```

## 配置选项

```python
@dataclass
class BenchmarkConfig:
    # 新增选项
    execution_mode: str = "print"  # "print" | "interactive"
    max_turns: int = 50
    auto_confirm: bool = True
    interactive_timeout: int = 600

    # 现有选项
    timeout_seconds: int = 600
    use_print_mode: bool = True  # deprecated
```

## 预期结果

| 指标 | --print | Interactive (预期) |
|------|---------|-------------------|
| Skill 调用率 | 0% | ~80% |
| Check-In 显示率 | ~10% | ~90% |
| 自动错误修复率 | 0% | ~60% |
| 平均执行时间 | 30s | 90s |
| 任务成功率 | ~70% | ~85% |

## 开放问题

1. `--dangerously-skip-permissions` 是否足够自动化所有场景？
2. 是否需要 `--no-interactive` 类似的标志？
3. 如何处理 agent 陷入循环的情况？
4. 是否需要向 Claude Code 团队反馈 benchmark 用例？

## 参考

- Claude Code CLI 文档
- [pexpect](https://pexpect.readthedocs.io/) - Python expect 库
- [pty](https://docs.python.org/3/library/pty.html) - Python PTY 模块
