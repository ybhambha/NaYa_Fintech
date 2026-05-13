from setuptools import setup, find_packages

setup(
    name="semisector",
    version="1.0.0",
    description="Semiconductor / Power / Memory Sector Opportunity Analyzer",
    author="ybhambha",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "yfinance>=0.2.38",
        "pandas>=2.0.0",
        "numpy>=1.26.0",
        "ta>=0.11.0",
        "tabulate>=0.9.0",
        "colorama>=0.4.6",
    ],
    entry_points={
        "console_scripts": [
            "semisector=main:main",
        ],
    },
)
