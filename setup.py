#!/usr/bin/env python3
"""
Setup script for cli-anything-anylogic

Install (dev mode):
    pip install -e .
"""

from pathlib import Path
from setuptools import setup, find_namespace_packages

ROOT = Path(__file__).parent
README = ROOT / "cli_anything/anylogic/README.md"

long_description = README.read_text(encoding="utf-8") if README.exists() else ""

setup(
    name="cli-anything-anylogic",
    version="1.0.0",
    description="CLI harness for AnyLogic - edit .alp simulation models and run them in the AnyLogic IDE "
                "via its Design-Time Python API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="cli-anything contributors",
    author_email="",
    url="https://github.com/rjmolinag0213r/anylogic-cli",
    license="Apache-2.0",
    packages=find_namespace_packages(include=("cli_anything.*",)),
    python_requires=">=3.10",
    install_requires=[
        "click>=8.1",
        "prompt-toolkit>=3.0",
        "lxml>=4.9",
        "py4j>=0.10.9",
    ],
    extras_require={"dev": ["pytest>=7"]},
    entry_points={
        "console_scripts": [
            "cli-anything-anylogic=cli_anything.anylogic.anylogic_cli:main",
        ],
    },
    package_data={"cli_anything.anylogic": ["skills/*.md"]},
    include_package_data=True,
    zip_safe=False,
    keywords=["cli", "anylogic", "simulation", "agent-based", "discrete-event", "system-dynamics"],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
    ],
)
