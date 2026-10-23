from htv_common.stall_guard import StallGuard


def test_regular_ticks_never_defer():
    g = StallGuard(0.3)
    assert not any(g.should_defer(t * 0.05) for t in range(100))


def test_single_stall_defers_once():
    g = StallGuard(0.3)
    g.should_defer(0.0)
    assert g.should_defer(1.0)
    assert not g.should_defer(1.05)
    assert g.stall_count == 1


def test_consecutive_stalls_do_not_defer_twice():
    g = StallGuard(0.3)
    g.should_defer(0.0)
    assert g.should_defer(1.0)
    assert not g.should_defer(2.0)
