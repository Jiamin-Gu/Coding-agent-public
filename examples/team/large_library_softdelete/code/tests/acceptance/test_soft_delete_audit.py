"""验收测试：软删除、恢复、审计日志（对应需求 1-5）。

子任务不得修改本文件；它是“完成”的判定标准。
"""

import pytest

from library.app import Library
from library.errors import NotFoundError


ALL_ENTITIES = (
    "branch",
    "book",
    "member",
    "staff",
    "supplier",
    "loan",
    "fine",
    "reservation",
)

# 直接往 Repo 里 add 所需的字段（绕过 service 校验，用于测试存储层）。
SAMPLE = {
    "branch": dict(name="总馆", city="北京"),
    "book": dict(title="三体", author="刘慈欣", isbn="9787536692930", branch_id=1),
    "member": dict(name="小明", email="xm@example.com"),
    "staff": dict(name="老王", branch_id=1),
    "supplier": dict(name="书商甲"),
    "loan": dict(book_id=1, member_id=1, due="2026-01-15"),
    "fine": dict(member_id=1, amount=500),
    "reservation": dict(book_id=1, member_id=1),
}


class FixedClock:
    def __init__(self, now="2026-01-01T10:00:00", today="2026-01-01"):
        self._now = now
        self._today = today

    def now(self):
        return self._now

    def today(self):
        return self._today


@pytest.fixture
def lib():
    return Library(clock=FixedClock())


# ---------------------------------------------------------------- 需求 1：字段

@pytest.mark.parametrize("name", ALL_ENTITIES)
def test_entity_has_soft_delete_fields_with_defaults(lib, name):
    item = lib.repos[name].add(**SAMPLE[name])
    assert item.deleted is False
    assert item.deleted_at is None


# ------------------------------------------------ 需求 1+2：软删除与查询语义

@pytest.mark.parametrize("name", ALL_ENTITIES)
def test_delete_marks_instead_of_removing(lib, name):
    repo = lib.repos[name]
    item = repo.add(**SAMPLE[name])
    repo.delete(item.id)

    # 数据仍在，只是被标记
    assert item.deleted is True
    assert item.deleted_at == "2026-01-01T10:00:00"

    # get：默认 NotFoundError，include_deleted=True 能取到同一个对象
    with pytest.raises(NotFoundError):
        repo.get(item.id)
    assert repo.get(item.id, include_deleted=True) is item

    # list：默认不包含，include_deleted=True 包含
    assert repo.list() == []
    assert repo.list(include_deleted=True) == [item]

    # 不存在的 id，即使 include_deleted=True 也要报错
    with pytest.raises(NotFoundError):
        repo.get(999, include_deleted=True)


# ----------------------------------------------------------- 需求 3：恢复

@pytest.mark.parametrize("name", ALL_ENTITIES)
def test_restore_deleted_entity(lib, name):
    repo = lib.repos[name]
    item = repo.add(**SAMPLE[name])

    # 未被删除 / 不存在 -> NotFoundError
    with pytest.raises(NotFoundError):
        repo.restore(item.id)
    with pytest.raises(NotFoundError):
        repo.restore(999)

    repo.delete(item.id)
    restored = repo.restore(item.id)

    assert restored is item
    assert item.deleted is False
    assert item.deleted_at is None
    assert repo.get(item.id) is item
    assert repo.list() == [item]


def test_query_methods_exclude_deleted(lib):
    repos = lib.repos
    b = lib.branch.create("总馆", "北京")
    book = lib.book.create("三体", "刘慈欣", "9787536692930", b.id)
    m1 = lib.member.register("a", "a@x.com")
    m2 = lib.member.register("b", "b@x.com")
    staff = lib.staff.hire("王", b.id, "librarian")
    loan = repos["loan"].add(book_id=book.id, member_id=m1.id, due="2026-01-15")
    fine = repos["fine"].add(member_id=m1.id, amount=300)
    res = repos["reservation"].add(book_id=book.id, member_id=m1.id)

    repos["book"].delete(book.id)
    repos["member"].delete(m1.id)
    repos["staff"].delete(staff.id)
    repos["loan"].delete(loan.id)
    repos["fine"].delete(fine.id)
    repos["reservation"].delete(res.id)

    assert repos["book"].by_branch(b.id) == []
    assert repos["member"].by_level("basic") == [m2]
    assert repos["staff"].by_branch(b.id) == []
    assert repos["loan"].for_book(book.id) == []
    assert repos["loan"].for_member(m1.id) == []
    assert repos["fine"].for_member(m1.id) == []
    assert repos["reservation"].for_member(m1.id) == []
    assert repos["reservation"].for_book(book.id) == []


# ------------------------------------------------------- 需求 4：审计日志

def test_library_exposes_audit(lib):
    assert lib.audit is not None
    assert hasattr(lib.audit, "entries")


@pytest.mark.parametrize("name", ALL_ENTITIES)
def test_audit_entity_type_is_repo_key(lib, name):
    item = lib.repos[name].add(**SAMPLE[name])
    entries = lib.audit.entries(entity_type=name)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.entity_type == name
    assert entry.entity_id == item.id
    assert entry.action == "create"
    assert entry.at == "2026-01-01T10:00:00"


def test_audit_records_create_update_delete_restore_in_order(lib):
    repo = lib.repos["book"]
    b = lib.branch.create("总馆", "北京")
    book = lib.book.create("三体", "刘慈欣", "9787536692930", b.id)  # create
    lib.book.move(book.id, b.id)  # update
    repo.delete(book.id)  # delete
    repo.restore(book.id)  # restore

    entries = lib.audit.entries(entity_type="book")
    assert [e.action for e in entries] == ["create", "update", "delete", "restore"]
    assert all(e.entity_type == "book" for e in entries)
    assert all(e.entity_id == book.id for e in entries)
    assert all(e.at == "2026-01-01T10:00:00" for e in entries)


def test_audit_filters(lib):
    b1 = lib.branch.create("总馆", "北京")
    b2 = lib.branch.create("分馆", "上海")
    s = lib.supplier.create("书商")

    # 按 entity_type 过滤
    assert [e.entity_id for e in lib.audit.entries(entity_type="branch")] == [b1.id, b2.id]
    assert [e.entity_id for e in lib.audit.entries(entity_type="supplier")] == [s.id]
    # 按 action 过滤（按记录顺序）
    assert [e.action for e in lib.audit.entries(action="create")] == ["create"] * 3
    # 按 entity_id 过滤
    assert [e.entity_type for e in lib.audit.entries(entity_id=b2.id)] == ["branch"]
    # 多个条件为“与”
    assert [e.entity_id for e in lib.audit.entries(entity_type="branch", entity_id=b2.id)] == [b2.id]
    # 没有匹配时返回空列表
    assert lib.audit.entries(entity_type="book") == []
    # 全量按记录顺序
    everything = lib.audit.entries()
    assert [e.entity_type for e in everything] == ["branch", "branch", "supplier"]


# ------------------------------------------- 需求 5：业务规则把已删除当不存在

def test_deleted_book_and_member_unusable_in_services(lib):
    b = lib.branch.create("总馆", "北京")
    book = lib.book.create("三体", "刘慈欣", "9787536692930", b.id)
    m = lib.member.register("a", "a@x.com")

    lib.book.remove(book.id)
    with pytest.raises(NotFoundError):
        lib.loan.borrow(book.id, m.id)
    with pytest.raises(NotFoundError):
        lib.reservation.reserve(book.id, m.id)

    lib.member.remove(m.id)
    with pytest.raises(NotFoundError):
        lib.fine.issue(m.id, 100)


def test_deleted_branch_unusable_in_services(lib):
    b = lib.branch.create("总馆", "北京")
    lib.branch.remove(b.id)
    with pytest.raises(NotFoundError):
        lib.book.create("三体", "刘慈欣", "9787536692930", b.id)
    with pytest.raises(NotFoundError):
        lib.staff.hire("王", b.id)


def test_deleted_member_treated_as_nonexistent_for_uniqueness(lib):
    m = lib.member.register("a", "a@x.com")
    lib.member.remove(m.id)
    again = lib.member.register("b", "a@x.com")
    assert again.email == "a@x.com"


def test_existing_suite_style_smoke(lib):
    """复刻 tests/test_existing.py 的核心用法，确保行为兼容。"""
    b = lib.branch.create("总馆", "北京")
    book = lib.book.create("三体", "刘慈欣", "9787536692930", b.id)
    m = lib.member.register("a", "a@x.com")
    loan = lib.loan.borrow(book.id, m.id)
    assert loan.due == "2026-01-15" and lib.loan.active_count(m.id) == 1
    lib.loan.give_back(loan.id)
    lib.loan.borrow(book.id, m.id)
