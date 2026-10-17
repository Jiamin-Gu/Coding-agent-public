# 图书馆管理系统

分层结构：

- `library/models/`：实体（数据类）
- `library/repos/`：每种实体的存储，提供 add / get / list / update / delete 以及一些查询方法
- `library/services/`：业务规则（校验、跨实体的检查）
- `library/cli/`：命令行输出格式
- `library/app.py`：`Library` 把所有存储和服务组装在一起
- `library/clock.py`：当前时间（测试时可以替换）

运行测试：`python -m pytest -q`
