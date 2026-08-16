"""Package setup for Jarvis.

Not required for running the API (use requirements.txt + venv for
that) — this exists so `src` can be installed as an importable
package if another project ever needs to depend on it.
"""

from setuptools import find_packages, setup

setup(
    name="jarvis",
    version="0.1.0",
    description="Jarvis — AI agent orchestration system (Phase 0)",
    packages=find_packages(include=["src", "src.*"]),
    python_requires=">=3.11",
)
