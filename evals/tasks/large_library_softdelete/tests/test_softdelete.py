import pytest

from library.app import Library
from library.errors import NotFoundError, ValidationError

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
# 每个 Repo 的额外查询方法：(方法名, 参数)
QUERIES = {
    "book": [("by_branch", 1)], "member": [("by_level", "basic")], "staff": [("by_branch", 1)],
    "loan": [("for_book", 1), ("for_member", 1)], "fine": [("for_member", 1)],
    "reservation": [("for_member", 1), ("for_book", 1)],
}


class Clock:
    def __init__(self):
        self.t = "2026-01-01T10:00:00"

    def now(self):
        return self.t

    def today(self):
        return self.t[:10]


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def lib(clock):
    return Library(clock=clock)


@pytest.mark.parametrize("name", list(SAMPLE))
def test_soft_delete_and_restore(lib, clock, name):
    repo = lib.repos[name]
    keep = repo.add(**SAMPLE[name])
    item = repo.add(**SAMPLE[name])
    assert item.deleted is False and item.deleted_at is None
    clock.t = "2026-02-03T04:05:06"
    repo.delete(item.id)
    with pytest.raises(NotFoundError):
        repo.get(item.id)
    gone = repo.get(item.id, include_deleted=True)
    assert gone.deleted is True and gone.deleted_at == "2026-02-03T04:05:06"
    assert repo.list() == [keep]
    assert [i.id for i in repo.list(include_deleted=True)] == [keep.id, item.id]
    with pytest.raises(NotFoundError):
        repo.delete(item.id)                     # 已删除的不能再删
    restored = repo.restore(item.id)
    assert restored is gone and restored.deleted is False and restored.deleted_at is None
    assert repo.get(item.id) is item
    with pytest.raises(NotFoundError):
        repo.restore(item.id)                    # 没被删除，不能恢复
    with pytest.raises(NotFoundError):
        repo.restore(999)


@pytest.mark.parametrize("name", [n for n in QUERIES])
def test_queries_hide_deleted(lib, name):
    repo = lib.repos[name]
    a = repo.add(**SAMPLE[name])
    b = repo.add(**SAMPLE[name])
    repo.delete(a.id)
    for method, arg in QUERIES[name]:
        assert getattr(repo, method)(arg) == [b], f"{name}.{method} 返回了已删除的实体"


@pytest.mark.parametrize("name", list(SAMPLE))
def test_audit_log_per_entity(lib, clock, name):
    repo = lib.repos[name]
    item = repo.add(**SAMPLE[name])
    field, value = next(iter(SAMPLE[name].items()))
    clock.t = "2026-03-01T00:00:00"
    repo.update(item.id, **{field: value})
    repo.delete(item.id)
    clock.t = "2026-03-02T00:00:00"
    repo.restore(item.id)
    entries = lib.audit.entries(entity_type=name)
    assert [(e.entity_type, e.entity_id, e.action) for e in entries] == [
        (name, item.id, "create"), (name, item.id, "update"), (name, item.id, "delete"), (name, item.id, "restore")]
    assert [e.at for e in entries] == ["2026-01-01T10:00:00", "2026-03-01T00:00:00", "2026-03-01T00:00:00",
                                       "2026-03-02T00:00:00"]


def test_audit_filters_and_order(lib):
    b = lib.repos["branch"].add(name="总馆", city="北京")
    s = lib.repos["supplier"].add(name="甲")
    lib.repos["branch"].delete(b.id)
    lib.repos["supplier"].update(s.id, name="乙")
    assert [(e.entity_type, e.action) for e in lib.audit.entries()] == [
        ("branch", "create"), ("supplier", "create"), ("branch", "delete"), ("supplier", "update")]
    assert [e.entity_type for e in lib.audit.entries(action="create")] == ["branch", "supplier"]
    assert lib.audit.entries(entity_type="branch", entity_id=999) == []
    assert len(lib.audit.entries(entity_id=b.id)) == 4   # 分馆和供应商的 id 都是 1


def test_services_respect_soft_delete(lib):
    br = lib.branch.create("总馆", "北京")
    book = lib.book.create("三体", "刘慈欣", "9787536692930", br.id)
    m = lib.member.register("a", "a@x.com")
    lib.book.remove(book.id)
    with pytest.raises(NotFoundError):
        lib.loan.borrow(book.id, m.id)
    with pytest.raises(NotFoundError):
        lib.reservation.reserve(book.id, m.id)
    lib.repos["book"].restore(book.id)
    loan = lib.loan.borrow(book.id, m.id)
    # 删除借阅记录后，这本书视为没有借出
    lib.loan.remove(loan.id)
    lib.loan.borrow(book.id, m.id)
    # 删除分馆后不能再往里加书或员工
    lib.branch.remove(br.id)
    with pytest.raises(NotFoundError):
        lib.book.create("x", "y", "9787536692930", br.id)
    with pytest.raises(NotFoundError):
        lib.staff.hire("王", br.id)
    # 已删除会员的邮箱：恢复前不算重复（被删的不在 list 里）
    lib.member.remove(m.id)
    lib.member.register("b", "a@x.com")


def test_deleted_fines_and_reservations_not_counted(lib):
    br = lib.branch.create("总馆", "北京")
    m = lib.member.register("a", "a@x.com")
    f = lib.fine.issue(m.id, 300)
    lib.fine.issue(m.id, 200)
    lib.fine.remove(f.id)
    assert lib.fine.outstanding(m.id) == 200
    books = [lib.book.create(f"书{i}", "某人", "9787536692930", br.id) for i in range(4)]
    rs = [lib.reservation.reserve(bk.id, m.id) for bk in books[:3]]
    lib.reservation.cancel(rs[0].id)
    lib.reservation.reserve(books[3].id, m.id)   # 取消（软删除）的预约不占名额


def test_staff_manager_rule_ignores_deleted(lib):
    br = lib.branch.create("总馆", "北京")
    boss = lib.staff.hire("王", br.id, "manager")
    lib.staff.remove(boss.id)
    lib.staff.hire("李", br.id, "manager")
    with pytest.raises(ValidationError):
        lib.staff.hire("赵", br.id, "manager")
