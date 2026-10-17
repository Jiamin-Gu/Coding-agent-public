class LibraryError(Exception):
    """图书馆系统的基础异常。"""


class NotFoundError(LibraryError):
    pass


class ValidationError(LibraryError):
    pass
