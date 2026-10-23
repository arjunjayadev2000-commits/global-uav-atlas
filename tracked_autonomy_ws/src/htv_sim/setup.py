from setuptools import find_packages, setup

package_name = "htv_sim"

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
    description="Simulated heavy tracked vehicle plant and simulation-only support nodes.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "tracked_vehicle_sim_node = htv_sim.tracked_vehicle_sim_node:main",
            "sim_health_stub_node = htv_sim.sim_health_stub_node:main",
        ],
    },
)
