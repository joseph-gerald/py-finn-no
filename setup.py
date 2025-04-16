from setuptools import setup, find_packages

setup(
    name="finn",
    version="0.0.0",
    packages=find_packages(),
    install_requires=[
        "beautifulsoup4>=4.11.1",
        "requests>=2.28.1",
        "lxml>=4.9.1",
    ],
    python_requires=">=3.6",
) 