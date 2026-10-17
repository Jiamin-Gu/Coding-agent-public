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


class FixedClock:
    def now(self):
        return "2026-01-01T10:00:00"

    def today(self):
        return "2026-01-01"


@pytest.fixture
def lib():
    return Library(clock=FixedClock())


@pytest.mark.parametrize("name", list(SAMPLE))
def test_repo_crud(lib, name):
    repo = lib.repos[name]
    item = repo.add(**SAMPLE[name])
    assert repo.get(item.id) is item and repo.list() == [item]
    repo.update(item.id, **{next(iter(SAMPLE[name])): SAMPLE[name][next(iter(SAMPLE[name]))]})
    with pytest.raises(ValueError):
        repo.update(item.id, nope=1)
    repo.delete(item.id)
    with pytest.raises(NotFoundError):
        repo.get(item.id)
    assert repo.list() == []


def test_book_rules(lib):
    b = lib.branch.create("总馆", "北京")
    with pytest.raises(ValidationError):
        lib.book.create("x", "y", "123", b.id)
    with pytest.raises(NotFoundError):
        lib.book.create("x", "y", "9787536692930", 99)
    book = lib.book.create("三体", "刘慈欣", "978-7-5366-9293-0", b.id)
    assert lib.repos["book"].by_branch(b.id) == [book]


def test_member_and_staff_rules(lib):
    lib.member.register("a", "a@x.com")
    with pytest.raises(ValidationError):
        lib.member.register("b", "a@x.com")
    with pytest.raises(ValidationError):
        lib.member.register("c", "bad-email")
    b = lib.branch.create("总馆", "北京")
    lib.staff.hire("王", b.id, "manager")
    with pytest.raises(ValidationError):
        lib.staff.hire("李", b.id, "manager")


def test_loans(lib):
    b = lib.branch.create("总馆", "北京")
    book = lib.book.create("三体", "刘慈欣", "9787536692930", b.id)
    m = lib.member.register("a", "a@x.com")
    loan = lib.loan.borrow(book.id, m.id)
    assert loan.due == "2026-01-15" and lib.loan.active_count(m.id) == 1
    with pytest.raises(ValidationError):
        lib.loan.borrow(book.id, m.id)
    lib.loan.give_back(loan.id)
    lib.loan.borrow(book.id, m.id)


def test_fines_and_reservations(lib):
    b = lib.branch.create("总馆", "北京")
    m = lib.member.register("a", "a@x.com")
    f = lib.fine.issue(m.id, 300)
    lib.fine.issue(m.id, 200)
    lib.fine.pay(f.id)
    assert lib.fine.outstanding(m.id) == 200
    books = [lib.book.create(f"书{i}", "某人", "9787536692930", b.id) for i in range(4)]
    for bk in books[:3]:
        lib.reservation.reserve(bk.id, m.id)
    with pytest.raises(ValidationError):
        lib.reservation.reserve(books[3].id, m.id)
