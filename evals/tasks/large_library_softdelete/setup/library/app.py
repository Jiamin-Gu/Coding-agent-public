from .clock import Clock
from .repos.branch_repo import BranchRepo
from .repos.book_repo import BookRepo
from .repos.member_repo import MemberRepo
from .repos.staff_repo import StaffRepo
from .repos.supplier_repo import SupplierRepo
from .repos.loan_repo import LoanRepo
from .repos.fine_repo import FineRepo
from .repos.reservation_repo import ReservationRepo
from .services.branch_service import BranchService
from .services.book_service import BookService
from .services.member_service import MemberService
from .services.staff_service import StaffService
from .services.supplier_service import SupplierService
from .services.loan_service import LoanService
from .services.fine_service import FineService
from .services.reservation_service import ReservationService


class Library:
    """把所有存储和业务服务组装在一起。repos 按实体名索引，例如 repos["book"]。"""

    def __init__(self, clock=None):
        self.clock = clock or Clock()
        self.repos = {
            "branch": BranchRepo(),
            "book": BookRepo(),
            "member": MemberRepo(),
            "staff": StaffRepo(),
            "supplier": SupplierRepo(),
            "loan": LoanRepo(),
            "fine": FineRepo(),
            "reservation": ReservationRepo(),
        }
        self.branch = BranchService(self.repos["branch"])
        self.book = BookService(self.repos["book"], self.repos["branch"])
        self.member = MemberService(self.repos["member"])
        self.staff = StaffService(self.repos["staff"], self.repos["branch"])
        self.supplier = SupplierService(self.repos["supplier"])
        self.loan = LoanService(self.repos["loan"], self.repos["book"], self.repos["member"], self.clock)
        self.fine = FineService(self.repos["fine"], self.repos["member"])
        self.reservation = ReservationService(self.repos["reservation"], self.repos["book"], self.repos["member"])
