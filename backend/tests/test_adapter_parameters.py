from generation.adapter import resolve_batch_shape


def test_rtx3090_batch_shape_keeps_small_requests_single_batch() -> None:
    assert resolve_batch_shape(2, 8) == (2, 1)
    assert resolve_batch_shape(8, 8) == (8, 1)


def test_rtx3090_batch_shape_splits_large_requests() -> None:
    assert resolve_batch_shape(10, 8) == (5, 2)
    assert resolve_batch_shape(13, 8) == (7, 2)
    assert resolve_batch_shape(16, 8) == (8, 2)
