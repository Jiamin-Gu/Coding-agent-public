from billing.core import calc_total
from billing.report import summary


def run():
    print(calc_total([(10, 2), (5, 1)]))
    print(summary({"A1": [(3, 3)]}))
    return calc_total([(1, 1)])


if __name__ == "__main__":
    run()
