这是一个图书馆管理系统（结构见 README.md）。请给所有 8 种实体加上**软删除、恢复和审计日志**：

1. **软删除**：所有存储（`library/repos/` 下的 8 个 Repo）的 `delete(id)` 不再真正删除数据，而是把实体标记为已删除：`deleted = True`，`deleted_at` 记为当时的 `clock.now()`。实体新增这两个字段，默认值分别是 `False` 和 `None`
2. **查询**：
   - `get(id)` 对已删除的实体抛出 `NotFoundError`；`get(id, include_deleted=True)` 可以取到已删除的实体
   - `list()` 默认不包含已删除的实体，`list(include_deleted=True)` 包含
   - 每个 Repo 里的其他查询方法（例如 `by_branch`、`for_member`）都不返回已删除的实体
3. **恢复**：每个 Repo 新增 `restore(id)`，把已删除的实体恢复（`deleted = False`，`deleted_at = None`）并返回它；实体不存在或没有被删除时抛出 `NotFoundError`
4. **审计日志**：新增 `library/audit.py`，提供 `AuditLog` 类：
   - 通过 `Library` 中的 Repo 进行的每一次 add、update、delete、restore 都要记录一条日志，`action` 分别是 `"create"`、`"update"`、`"delete"`、`"restore"`
   - 每条日志是一个对象，有 `entity_type`（实体名，即 `Library.repos` 的键，例如 `"book"`）、`entity_id`、`action`、`at`（当时的 `clock.now()`）四个属性
   - `AuditLog.entries(entity_type=None, entity_id=None, action=None)` 按条件过滤，按记录的先后顺序返回
   - `Library` 对象上要有 `audit` 属性，指向这个审计日志
5. 业务规则自然适用：已删除的图书、会员、分馆等，在业务服务里视为不存在（比如不能借已删除的书）

`tests/` 里的现有测试必须继续通过。
