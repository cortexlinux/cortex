import os

from setuptools import find_packages, setup

with open("README.md", encoding="utf-8") as fh:
    long_description = fh.read()

# Dependencies are now defined in pyproject.toml
# This is kept for backward compatibility but pyproject.toml is the source of truth
requirements = [
    "anthropic>=0.18.0",
    "openai>=1.0.0",
    "requests>=2.32.4",
    "PyYAML>=6.0.3",
    "python-dotenv>=1.0.0",
    "cryptography>=44.0.1",
    "rich>=13.0.0",
    "typing-extensions>=4.0.0",
]

setup(
    name="cortex-linux",
    version="0.1.0",
    author="Cortex Linux",
    author_email="mike@cortexlinux.com",
    description="AI-powered Linux command interpreter",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/cortexlinux/cortex",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Topic :: System :: Installation/Setup",
        "Topic :: System :: Systems Administration",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: POSIX :: Linux",
    ],
    python_requires=">=3.10",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "cortex=cortex.cli:main",
        ],
    },
    include_package_data=True,
)
