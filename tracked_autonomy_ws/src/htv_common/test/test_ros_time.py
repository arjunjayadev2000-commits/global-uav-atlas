import pytest
from htv_common.ros_time import from_seconds, to_seconds


@pytest.mark.parametrize("value", [0.0, 1.5, 1234.999999999, 1e9 + 0.25])
def test_round_trip(value):
    assert to_seconds(from_seconds(value)) == pytest.approx(value, abs=1e-6)


def test_nanosec_never_overflows():
    stamp = from_seconds(1.9999999999)
    assert 0 <= stamp.nanosec < 1_000_000_000
