from glob import glob

from setuptools import find_packages, setup

package_name = "htv_bringup"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.py")),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    extras_require={"test": ["pytest"]},
    zip_safe=True,
    maintainer="HTV research team",
    maintainer_email="arjunjayadev2000@gmail.com",
    description="Bring-up and system validation for the HTV research stack.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "graph_check = htv_bringup.graph_check:main",
            "reset_estop = htv_bringup.reset_estop:main",
        ],
    },
)
