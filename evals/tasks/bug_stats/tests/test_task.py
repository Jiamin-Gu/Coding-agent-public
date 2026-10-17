import pytest

from stats import mean, median, mode


def test_mean():
    assert mean([1, 2, 3, 4]) == 2.5


def test_median_odd_and_even():
    assert median([3, 1, 2]) == 2
    assert median([3, 1, 4, 2]) == 2.5


def test_median_does_not_mutate():
    data = [3, 1, 4, 2]
    median(data)
    assert data == [3, 1, 4, 2]


def test_mode():
    assert mode([1, 2, 2, 3]) == 2
    assert mode([5, 1, 1, 5, 3]) == 1   # 平局取最小


@pytest.mark.parametrize("fn", [mean, median, mode])
def test_empty_raises_value_error(fn):
    with pytest.raises(ValueError):
        fn([])
