from setuptools import find_packages, setup

package_name = "htv_safety"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    extras_require={"test": ["pytest"]},
    zip_safe=True,
    maintainer="HTV research team",
    maintainer_email="arjunjayadev2000@gmail.com",
    description="Independent safety subsystem for the HTV research stack.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "safety_supervisor_node = htv_safety.safety_supervisor_node:main",
            "command_limiter_node = htv_safety.command_limiter_node:main",
            "motion_arbitration_node = htv_safety.motion_arbitration_node:main",
            "operator_mode_node = htv_safety.operator_mode_node:main",
            "watchdog_node = htv_safety.watchdog_node:main",
            "geofence_monitor_node = htv_safety.geofence_monitor_node:main",
        ],
    },
)
