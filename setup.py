from setuptools import setup, find_packages
import os

base_dir = os.path.abspath(os.path.dirname(__file__))

# --- Safe version loading (no exec) ---
version = {}
version_path = os.path.join(base_dir, "intent_bus", "version.py")

with open(version_path, "r") as f:
    for line in f:
        if line.startswith("__version__"):
            version["__version__"] = line.split("=")[1].strip().strip('"\'')
            break

# --- Safe README loading ---
readme_path = os.path.join(base_dir, "README.md")
if os.path.exists(readme_path):
    with open(readme_path, encoding="utf-8") as f:
        long_description = f.read()
else:
    long_description = "Python SDK for Intent Bus"

setup(
    name="intent-bus",
    version=version["__version__"],
    description="Python SDK for Intent Bus — a dead-simple distributed job bus",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="dsecurity49",
    url="https://github.com/dsecurity49/Intent-Bus",
    project_urls={
        "Source": "https://github.com/dsecurity49/Intent-Bus-sdk",
        "Bug Tracker": "https://github.com/dsecurity49/Intent-Bus-sdk/issues",
    },
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "requests>=2.31.0",
    ],
    python_requires=">=3.7",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
