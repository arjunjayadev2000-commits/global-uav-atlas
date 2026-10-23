from glob import glob

from setuptools import find_packages, setup

package_name = "htv_gazebo"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/worlds", glob("worlds/*")),
        ("share/" + package_name + "/launch", glob("launch/*.py")),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
        ("share/" + package_name + "/scripts", glob("scripts/*.py")),
    ],
    install_requires=["setuptools"],
    extras_require={"test": ["pytest"]},
    zip_safe=True,
    maintainer="HTV research team",
    maintainer_email="arjunjayadev2000@gmail.com",
    description="Gazebo worlds and launch for the HTV research platform.",
    license="Apache-2.0",
)
