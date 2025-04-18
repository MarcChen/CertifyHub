# CertifyHub

A tool for scraping and serving certification exam practice questions.

## Overview

CertifyHub is designed to help you prepare for certification exams by:

1. Scraping exam practice questions from sites like ExamTopics
2. Organizing the content into a searchable format
3. Serving the content through a static web server

## Project Structure

```
certifyHub/
├── pyproject.toml        # Poetry dependency configuration
├── poetry.toml           # Poetry configuration
├── README.md             # This file
├── src/
│   ├── scraper/          # Scraping service
│   │   ├── __init__.py
│   │   └── examtopics.py # ExamTopics specific scraper
│   └── web/              # Web service for serving content
│       ├── __init__.py
│       └── server.py     # Static web server
└── tests/                # Test files
    ├── __init__.py
    └── test_scraper.py   # Tests for scraper functionality
```

## Getting Started

### Prerequisites

- Python 3.9+
- Poetry for dependency management

### Installation

```bash
# Install dependencies
poetry install
```

### Running the Scraper

```bash
poetry run python -m src.scraper.examtopics
```

### Running the Web Server

```bash
poetry run python -m src.web.server
```

## License

MIT