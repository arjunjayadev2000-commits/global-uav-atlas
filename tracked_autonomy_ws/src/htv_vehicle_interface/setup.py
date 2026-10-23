from setuptools import find_packages, setup

package_name = "htv_vehicle_interface"

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
    description="Vehicle abstraction layer with a simulation-only backend.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "vehicle_interface_node = htv_vehicle_interface.vehicle_interface_node:main",
        ],
        # Backend registry. Only the simulated backend is provided here.
        "htv_vehicle_interface.backends": [
            "simulated = htv_vehicle_interface.simulated:SimulatedLegacyTrackedVehicleInterface",
        ],
    },
)
