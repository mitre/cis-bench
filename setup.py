"""Setup configuration for CIS Benchmark CLI."""

from pathlib import Path

from setuptools import find_packages, setup

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="cis-bench",
    version="1.0.0",
    description="CLI tool for fetching and managing CIS benchmarks from CIS WorkBench",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="MITRE SAF Team",
    author_email="saf@mitre.org",
    url="https://github.com/mitre/cis-bench",
    license="Apache-2.0",
    packages=find_packages(where="src"),  # src layout
    package_dir={"": "src"},  # Look for packages in src/
    # Include package data (schemas, etc.)
    package_data={
        "cis_bench": [
            "models/xccdf/*.py",
        ],
        "": [
            "schemas/*.xsd",
            "schemas/schema/cpe/2.3/*.xsd",
            "schemas/*.xml",
        ],
    },
    include_package_data=True,
    python_requires=">=3.8",
    install_requires=[
        # Core scraping
        "requests>=2.31.0",
        "beautifulsoup4>=4.12.2",
        "urllib3>=2.0.6",
        # Data modeling
        "pydantic>=2.0.0",
        # CLI
        "click>=8.1.0",
        "rich>=13.7.0",
        "questionary>=2.0.0",
        # Authentication
        "browser-cookie3>=0.19.0",
        # Export formats
        "PyYAML>=6.0.0",
        "xsdata[cli,lxml]>=24.0.0",
        "lxml>=5.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-mock>=3.12.0",
            "pytest-cov>=4.1.0",
            "black>=23.0.0",
            "mypy>=1.0.0",
            "flake8>=6.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "cis-bench=cis_bench.cli.app:cli",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "Intended Audience :: System Administrators",
        "Topic :: Security",
        "Topic :: Software Development :: Testing",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Security",
        "Topic :: System :: Systems Administration",
        "Topic :: Utilities",
    ],
    keywords="cis benchmark security compliance xccdf scap nist mitre",
)
