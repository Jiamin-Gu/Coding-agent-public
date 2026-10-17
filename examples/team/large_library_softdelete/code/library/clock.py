from datetime import date, datetime


class Clock:
    """当前时间。测试时可以换成固定时间的对象，只要提供同样的两个方法。"""

    def now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def today(self) -> str:
        return date.today().isoformat()
