"""
Setup script para OSINT Suite
"""

from setuptools import setup, find_packages

with open("README_OSINT_SUITE.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="osint-suite",
    version="1.0.0",
    author="OSINT Suite Team",
    description="Suite de herramientas OSINT - Excluye temas de redes de internet",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/jivoi/awesome-osint",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Information Technology",
        "Topic :: Security",
        "Topic :: Internet :: WWW/HTTP :: Indexing/Search",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.7",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "osint-suite=osint_suite.main:main",
            "osint-username=osint_suite.username_search:main",
            "osint-email=osint_suite.email_osint:main",
            "osint-phone=osint_suite.phone_investigator:main",
            "osint-social=osint_suite.social_analyzer:main",
            "osint-image=osint_suite.image_metadata:main",
            "osint-document=osint_suite.document_analyzer:main",
            "osint-geo=osint_suite.geolocation_helper:main",
            "osint-breach=osint_suite.breach_checker:main",
            "osint-company=osint_suite.company_research:main",
        ],
    },
    keywords="osint intelligence investigation security research",
    project_urls={
        "Bug Reports": "https://github.com/jivoi/awesome-osint/issues",
        "Source": "https://github.com/jivoi/awesome-osint",
    },
)
