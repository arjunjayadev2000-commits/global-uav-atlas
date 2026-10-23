from htv_safety.heartbeat_monitor import HeartbeatMonitor, Severity


def monitor(grace=5.0):
    m = HeartbeatMonitor(
        {"supervisor": Severity.CRITICAL, "nav": Severity.MAJOR, "logger": Severity.MINOR},
        timeout=0.5,
        startup_grace=grace,
    )
    m.start(0.0)
    return m


def beat_all(m, now):
    for name in ("supervisor", "nav", "logger"):
        m.beat(name, True, now)


def test_ok_when_all_fresh():
    m = monitor(grace=0.0)
    beat_all(m, 1.0)
    report = m.evaluate(1.2)
    assert report.stale == [] and report.worst == Severity.NONE and not report.lost_critical


def test_not_started_is_tolerated_during_grace_then_reported_without_estop():
    m = monitor()
    for k in range(1, 60):  # regular 0.1 s ticks up to 5.9 s
        report = m.evaluate(k * 0.1)
        if k * 0.1 < 5.0:
            assert report.stale == []
    assert set(report.stale) == {"supervisor", "nav", "logger"}
    assert report.worst == Severity.CRITICAL
    assert not report.lost_critical


def test_lost_critical_heartbeat_requests_estop():
    m = monitor(grace=0.0)
    beat_all(m, 1.0)
    report = m.evaluate(2.0)
    assert report.lost_critical and report.worst == Severity.CRITICAL


def test_lost_major_heartbeat_does_not_estop():
    m = monitor(grace=0.0)
    beat_all(m, 1.0)
    m.beat("supervisor", True, 1.9)
    m.beat("logger", True, 1.9)
    report = m.evaluate(2.0)
    assert report.stale == ["nav"] and report.worst == Severity.MAJOR and not report.lost_critical


def test_unhealthy_critical_node_requests_estop_and_recovers():
    m = monitor(grace=0.0)
    beat_all(m, 1.0)
    m.beat("supervisor", False, 1.1)
    assert m.evaluate(1.2).lost_critical
    m.beat("supervisor", True, 1.3)
    assert not m.evaluate(1.4).lost_critical


def test_clock_jump_backwards_is_stale():
    m = monitor(grace=0.0)
    beat_all(m, 10.0)
    assert m.evaluate(9.0).lost_critical


def test_unknown_nodes_ignored():
    m = monitor()
    m.beat("someone_else", True, 1.0)
    assert m.evaluate(1.0).stale == []


def test_single_stall_defers_one_evaluation_only():
    m = monitor(grace=0.0)
    beat_all(m, 1.0)
    assert not m.evaluate(1.1).lost_critical
    # Monitor stalls for 2 s: first evaluation after the stall is deferred...
    first = m.evaluate(3.1)
    assert first.deferred and not first.lost_critical
    # ...heartbeats queued during the stall are then processed.
    beat_all(m, 3.15)
    assert not m.evaluate(3.2).lost_critical


def test_persistent_stall_still_trips():
    m = monitor(grace=0.0)
    beat_all(m, 1.0)
    m.evaluate(1.1)
    assert m.evaluate(3.1).deferred
    second = m.evaluate(5.1)
    assert not second.deferred and second.lost_critical


def test_no_estop_during_startup_grace():
    m = monitor()
    beat_all(m, 0.1)
    for k in range(2, 45):  # silent from 0.1 s, still inside the 5 s grace
        assert not m.evaluate(k * 0.1).lost_critical
