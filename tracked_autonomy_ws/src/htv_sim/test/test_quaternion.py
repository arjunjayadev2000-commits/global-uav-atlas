import math
from types import SimpleNamespace

import pytest
from htv_sim.tracked_vehicle_sim_node import quaternion_pitch, yaw_to_quaternion


def test_yaw_quaternion_is_unit():
    q = yaw_to_quaternion(1.2)
    assert sum(c * c for c in q) == pytest.approx(1.0)


@pytest.mark.parametrize("pitch", [-0.3, 0.0, 0.25])
def test_pitch_extraction(pitch):
    q = SimpleNamespace(x=0.0, y=math.sin(pitch / 2), z=0.0, w=math.cos(pitch / 2))
    assert quaternion_pitch(q) == pytest.approx(pitch)
