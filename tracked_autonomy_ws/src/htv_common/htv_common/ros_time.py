"""Conversions between ROS time messages and float seconds."""

from __future__ import annotations

from builtin_interfaces.msg import Time


def to_seconds(stamp: Time) -> float:
    return float(stamp.sec) + float(stamp.nanosec) * 1e-9


def from_seconds(seconds: float) -> Time:
    sec = int(seconds // 1)
    nanosec = round((seconds - sec) * 1e9)
    if nanosec >= 1_000_000_000:
        sec += 1
        nanosec -= 1_000_000_000
    return Time(sec=sec, nanosec=nanosec)


def now_seconds(node) -> float:
    return node.get_clock().now().nanoseconds * 1e-9


def clock_ready(node) -> bool:
    """False while a sim-time node has not yet received /clock (time reads 0)."""
    return node.get_clock().now().nanoseconds > 0
