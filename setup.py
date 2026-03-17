from setuptools import find_packages, setup


setup(
    name="klix-scraper-service",
    version="0.1.0",
    packages=find_packages(include=["app", "app.*"]),
    install_requires=[
        "apscheduler>=3.10,<4.0",
        "fastapi>=0.115,<1.0",
        "feedparser>=6.0,<7.0",
        "httpx>=0.27,<0.28",
        "pydantic>=2.8,<3.0",
        "pydantic-settings>=2.3,<3.0",
        "python-dateutil>=2.9,<3.0",
        "sqlalchemy>=2.0,<3.0",
        "uvicorn[standard]>=0.30,<1.0",
    ],
    extras_require={
        "postgres": ["psycopg[binary]>=3.2,<4.0"],
        "test": ["pytest>=8.2,<9.0"],
    },
)
