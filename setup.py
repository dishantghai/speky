#!/usr/bin/env python3
"""
SPEKY Setup Script
Install SPEKY globally so it can be used from any project directory.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

setup(
    name="speky",
    version="0.7.4",
    description="Speky-AI-Assisted Scalable Engineering Framework - Thin orchestration layer for spec-driven development",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="SPEKY Contributors",
    url="https://github.com/dishantghai/speky",
    py_modules=["speky", "speky_llm"],
    packages=["speky_core"],
    package_data={"speky_core": ["skills/*/SKILL.md"]},
    python_requires=">=3.8",
    install_requires=[
        "anthropic>=0.39.0",
        "openai>=1.0.0",
        "pyyaml>=6.0",
        "requests>=2.31.0",
    ],
    entry_points={
        "console_scripts": [
            "speky=speky:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    keywords="ai development framework orchestration spec-driven",
)
