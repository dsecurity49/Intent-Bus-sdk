from setuptools import setup, find_packages

setup(
    name="intent-bus",
    version="1.0.1",
    description="Python SDK for Intent Bus — a dead-simple distributed job bus",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="dsecurity49",
    url="https://github.com/dsecurity49/Intent-Bus",
    packages=find_packages(),
    install_requires=["requests>=2.28.0"],
    python_requires=">=3.7",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
