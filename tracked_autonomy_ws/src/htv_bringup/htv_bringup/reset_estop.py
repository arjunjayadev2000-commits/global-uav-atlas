"""CLI: explicit operator reset of a latched emergency stop (supervisor first, then vehicle).

    ros2 run htv_bringup reset_estop --operator alice
"""

from __future__ import annotations

import argparse
import sys

import rclpy
from htv_interfaces.srv import ResetEmergencyStop


def call(node, name: str, operator: str) -> tuple[bool, str]:
    client = node.create_client(ResetEmergencyStop, name)
    if not client.wait_for_service(timeout_sec=5.0):
        return False, f"{name} unavailable"
    future = client.call_async(ResetEmergencyStop.Request(operator_id=operator, confirmation="RESET"))
    rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
    result = future.result()
    return (result.success, result.message) if result else (False, f"{name} timed out")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator", required=True, help="operator identifier (logged)")
    args = parser.parse_args(argv)
    answer = input("Type RESET to confirm the vehicle area is clear and reset the emergency stop: ")
    if answer.strip() != "RESET":
        print("aborted")
        return 1
    rclpy.init()
    node = rclpy.create_node("htv_reset_estop")
    try:
        for service in ("/safety/reset_emergency_stop", "/vehicle/reset_emergency_stop"):
            ok, msg = call(node, service, args.operator)
            print(f"{service}: {'OK' if ok else 'REFUSED'} - {msg}")
            if not ok:
                return 1
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    print("Reset complete. Autonomy remains disabled until /autonomy/enable is called.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
