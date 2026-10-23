"""CLI: validate the live ROS graph against the command-chain rules.

    ros2 run htv_bringup graph_check [--timeout 10]
"""

from __future__ import annotations

import argparse
import sys
import time

import rclpy

from .graph_rules import GRAPH_RULES, REQUIRED_PUBLISHERS, violations


def snapshot(node) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    pubs: dict[str, set[str]] = {}
    subs: dict[str, set[str]] = {}
    for topic in set(GRAPH_RULES) | set(REQUIRED_PUBLISHERS):
        pubs[topic] = {i.node_name for i in node.get_publishers_info_by_topic(topic)}
        subs[topic] = {i.node_name for i in node.get_subscriptions_info_by_topic(topic)}
    return pubs, subs


def check(node, timeout: float) -> list[str]:
    deadline = time.monotonic() + timeout
    problems: list[str] = []
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.2)
        problems = violations(*snapshot(node))
        if not problems:
            return []
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)
    rclpy.init()
    node = rclpy.create_node("graph_check")
    try:
        problems = check(node, args.timeout)
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    if problems:
        print("ROS graph INVALID:")
        for p in problems:
            print("  -", p)
        return 1
    print("ROS graph valid: command chain intact, no bypass paths.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
