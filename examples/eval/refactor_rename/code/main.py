from billing.core import compute_total
from billing.report import summary


def run():
    print(compute_total([(10, 2), (5, 1)]))
    print(summary({"A1": [(3, 3)]}))
    return compute_total([(1, 1)])


if __name__ == "__main__":
    run()
