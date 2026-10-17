import copy

from intervals import merge_intervals


def test_examples():
    assert merge_intervals([[1, 3], [2, 6], [8, 10], [15, 18]]) == [[1, 6], [8, 10], [15, 18]]
    assert merge_intervals([[1, 4], [4, 5]]) == [[1, 5]]


def test_unsorted_and_contained():
    assert merge_intervals([[8, 10], [1, 10], [2, 3]]) == [[1, 10]]
    assert merge_intervals([[5, 6], [1, 2], [3, 4]]) == [[1, 2], [3, 4], [5, 6]]


def test_edge_cases():
    assert merge_intervals([]) == []
    assert merge_intervals([[1, 1]]) == [[1, 1]]


def test_input_not_mutated():
    data = [[3, 5], [1, 4]]
    before = copy.deepcopy(data)
    merge_intervals(data)
    assert data == before
