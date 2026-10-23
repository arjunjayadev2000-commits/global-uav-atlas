"""Uniform node entry point with clean shutdown."""

from __future__ import annotations

import rclpy
from rclpy.executors import ExternalShutdownException


def run_node(node_factory, args=None) -> None:
    rclpy.init(args=args)
    node = node_factory()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except Exception:
        # A callback racing the SIGINT teardown can fail inside rclpy; that is a
        # clean exit. Any error while the context is still valid is a real fault.
        if rclpy.ok():
            raise
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
