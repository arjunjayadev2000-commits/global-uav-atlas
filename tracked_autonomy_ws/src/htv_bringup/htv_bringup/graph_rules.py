"""ROS graph rules that enforce the single, non-bypassable command chain.

Each rule: topic -> (allowed publisher node names, allowed subscriber node names).
``None`` means "not restricted". Node names are compared without namespace.
"""

from __future__ import annotations

GRAPH_RULES: dict[str, tuple[set[str] | None, set[str] | None]] = {
    # Only the safety supervisor may consume planner output.
    "/cmd_vel_nav": (None, {"safety_supervisor"}),
    "/safety/gated_cmd": ({"safety_supervisor"}, {"command_limiter"}),
    "/control/limited_cmd": ({"command_limiter"}, {"motion_arbitration"}),
    # The vehicle abstraction layer input has exactly one producer.
    "/safe_cmd_vel": ({"motion_arbitration"}, {"vehicle_interface"}),
    # Simulated actuation is produced only by the vehicle interface.
    "/sim/track_demand": ({"vehicle_interface"}, {"tracked_vehicle_sim"}),
    "/safety/status": ({"safety_supervisor"}, None),
}

# Publishers that must exist for the graph to be considered complete.
REQUIRED_PUBLISHERS = {
    "/safety/gated_cmd": "safety_supervisor",
    "/control/limited_cmd": "command_limiter",
    "/safe_cmd_vel": "motion_arbitration",
    "/sim/track_demand": "vehicle_interface",
    "/vehicle/track_feedback": "tracked_vehicle_sim",
    "/safety/status": "safety_supervisor",
    "/watchdog/status": "watchdog",
    "/autonomy/operator_state": "operator_mode",
}

# Tooling nodes (CLI, rosbag, graph checker) may subscribe to anything.
OBSERVER_PREFIXES = ("_ros2cli", "rosbag2", "ros2bag", "graph_check", "htv_test", "rqt", "rviz", "foxglove")


def violations(publishers: dict[str, set[str]], subscribers: dict[str, set[str]]) -> list[str]:
    """Return human-readable rule violations for the observed graph."""
    problems = []
    for topic, (allowed_pubs, allowed_subs) in GRAPH_RULES.items():
        pubs = {n for n in publishers.get(topic, set()) if not n.startswith(OBSERVER_PREFIXES)}
        subs = {n for n in subscribers.get(topic, set()) if not n.startswith(OBSERVER_PREFIXES)}
        if allowed_pubs is not None and pubs - allowed_pubs:
            problems.append(f"{topic}: unauthorised publisher(s) {sorted(pubs - allowed_pubs)}")
        if allowed_subs is not None and subs - allowed_subs:
            problems.append(f"{topic}: unauthorised subscriber(s) {sorted(subs - allowed_subs)}")
    for topic, node in REQUIRED_PUBLISHERS.items():
        if node not in publishers.get(topic, set()):
            problems.append(f"{topic}: missing required publisher '{node}'")
    return problems
