from setuptools import setup, find_packages
import os

# Safely read the version without importing the package to avoid circular dependencies
version_file = os.path.join(os.path.dirname(__file__), "intent_bus", "version.py")
version = {}
with open(version_file) as f:
    exec(f.read(), version)

setup(
    name="intent-bus",
    version=version["__version__"],
    description="Python SDK for Intent Bus — a dead-simple distributed job bus",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="dsecurity49",
    url="https://github.com/dsecurity49/Intent-Bus",
    project_urls={
        "Source": "https://github.com/dsecurity49/intent-bus-sdk",
        "Main Project": "https://github.com/dsecurity49/Intent-Bus",
    },
    packages=find_packages(),
    install_requires=["requests>=2.31.0"],
    python_requires=">=3.7",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
