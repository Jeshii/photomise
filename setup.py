from setuptools import find_packages, setup

setup(
    name="photomise",
    version="0.1.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "photomise=photomise.cli.main:app",
        ],
    },
)
