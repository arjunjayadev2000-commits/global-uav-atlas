from htv_bringup.graph_rules import REQUIRED_PUBLISHERS, violations


def healthy_graph():
    pubs = {topic: {node} for topic, node in REQUIRED_PUBLISHERS.items()}
    pubs["/cmd_vel_nav"] = {"controller_server"}
    subs = {
        "/cmd_vel_nav": {"safety_supervisor"},
        "/safety/gated_cmd": {"command_limiter"},
        "/control/limited_cmd": {"motion_arbitration"},
        "/safe_cmd_vel": {"vehicle_interface"},
        "/sim/track_demand": {"tracked_vehicle_sim"},
    }
    return pubs, subs


def test_healthy_graph_has_no_violations():
    assert violations(*healthy_graph()) == []


def test_bypass_publisher_on_safe_cmd_vel_is_detected():
    pubs, subs = healthy_graph()
    pubs["/safe_cmd_vel"].add("controller_server")
    assert any("unauthorised publisher" in v for v in violations(pubs, subs))


def test_direct_planner_consumer_is_detected():
    pubs, subs = healthy_graph()
    subs["/cmd_vel_nav"].add("vehicle_interface")
    assert any("/cmd_vel_nav" in v for v in violations(pubs, subs))


def test_observers_are_allowed_and_missing_publishers_reported():
    pubs, subs = healthy_graph()
    subs["/safe_cmd_vel"].add("rosbag2_recorder")
    assert violations(pubs, subs) == []
    del pubs["/safe_cmd_vel"]
    assert any("missing required publisher" in v for v in violations(pubs, subs))
