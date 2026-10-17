"""团队模式的岗位预设：子 agent 按现实中的工程职责分工。

两层：
- 质量岗位（团队模式下总是出场）：测试、安全审查。默认各 1 个，按项目规模增加
- 开发岗位（主 agent 按项目类型选）：前端、后端、数据库、命令行和工具库、文档。大项目里同一个岗位可以开多个，
  各负责一部分模块

每个岗位的职责说明会写进子 agent 的提示词。职责说明用英文写，和其他提示词保持一致。
"""
from dataclasses import dataclass

# 配比按实测调整：large_spec_shop 7 个实现任务配了 3 个测试岗位，测试岗位花掉全队 23% 的输入 token
TESTS_PER_MODULES = 8      # 大约每这么多个实现模块配 1 个测试子 agent
SECURITY_PER_MODULES = 8   # 大约每这么多个实现模块配 1 个安全审查子 agent
MAX_PER_QUALITY_ROLE = 3   # 每个质量岗位最多开几个


@dataclass(frozen=True)
class Role:
    id: str
    name: str
    quality: bool        # 质量岗位：团队模式下总是出场
    read_only: bool      # 只读：不能写任何文件（安全审查）
    duty: str
    max_steps: int | None = None  # 这个岗位的步数上限（不写就用团队的默认值）


ROLES: dict[str, Role] = {r.id: r for r in [
    Role("tester", "测试", quality=True, read_only=False, duty="""\
You are the team's tester.
- First assignment: write acceptance tests for your spec sections and the contracts, in the test files you own. \
One test per rule, roughly 10-25 tests per file, no exhaustive combinations; expect only what the spec or the \
contracts state. The implementation may not exist yet: check only that the tests are collected \
(`python -m pytest --collect-only -q`).
- The lead runs the acceptance suite itself. If it sends you failing tests to investigate, decide for each \
whether the test or the implementation is wrong (quote the spec section); fix a test only when it contradicts \
the spec, and report which module / task must change otherwise.
- Never change implementation files; never weaken a test to make it pass.""", max_steps=30),
    Role("security", "安全审查", quality=True, read_only=True, duty="""\
You are the team's security reviewer. You are read-only: you cannot modify any file.
Review the code for real vulnerabilities, for example: command injection (shell=True, string-built commands), \
SQL injection (string-built queries), path traversal (user input in file paths), unsafe deserialization \
(pickle, yaml.load, eval/exec on input), hard-coded secrets or credentials, secrets in logs, weak randomness for \
tokens, missing validation of untrusted input at trust boundaries, XSS / unescaped output in web pages, SSRF, \
overly broad file permissions, insecure temporary files.
For each finding post board_post(kind="question", to="lead") and include it in your final report: file:line, \
severity (high / medium / low), why it is exploitable here, and a concrete fix. Do not report style issues or \
theoretical risks that cannot be reached in this code. If you find nothing, say so explicitly.
Work by reading the code. Run a command only to confirm a specific suspected issue, at most 5 commands in \
total; do not run the test suite or explore behaviour by trial and error.""", max_steps=20),
    Role("frontend", "前端", quality=False, read_only=False, duty="""\
You are a frontend engineer: page structure, interaction, state, styling, accessibility. Call the backend only \
through the API contract; escape any data you render (no innerHTML with untrusted data); keep the UI usable \
when requests fail."""),
    Role("backend", "后端", quality=False, read_only=False, duty="""\
You are a backend engineer: endpoints and business logic exactly as the API contracts say, validation of all \
input at the boundary, clear error responses, correct status codes, no secrets in code, safe handling of \
concurrency and partial failures."""),
    Role("database", "数据库", quality=False, read_only=False, duty="""\
You are a database / data engineer: schema, migrations, constraints, indexes, transactions, persistence formats. \
Always use parameterized queries; make writes atomic; keep data formats backward compatible when required."""),
    Role("cli", "命令行与工具库", quality=False, read_only=False, duty="""\
You are a library / command-line engineer: a clean public API exactly as the contracts say, type hints, \
docstrings, argument parsing, exit codes, stdout vs stderr, helpful error messages."""),
    Role("docs", "文档", quality=False, read_only=False, duty="""\
You write user documentation (README, usage guides) that matches the actual code: read the code and the \
contracts, do not invent features, give runnable examples."""),
]}

QUALITY_ROLES = [r for r in ROLES.values() if r.quality]


def role_guide() -> str:
    """给主 agent 的岗位说明：有哪些岗位、数量规则。"""
    dev = ", ".join(f"{r.id} ({r.name})" for r in ROLES.values() if not r.quality)
    return (f"Roles: every task has a `role`. Development roles: {dev}; pick the ones this project needs, and use "
            f"several tasks of the same role for different modules when the project is large. Quality roles are "
            f"always present in team mode: `tester` (writes the acceptance tests) and `security` "
            f"(read-only review, reports findings). Plan about one tester per {TESTS_PER_MODULES} implementation "
            f"tasks and one security reviewer per {SECURITY_PER_MODULES} (at least one of each, at most "
            f"{MAX_PER_QUALITY_ROLE} of each).")
