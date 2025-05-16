"""
ExamTopics Scraper Package

This package provides tools to scrape certification exam questions from ExamTopics.
"""

from .config import CERTIFICATION_CONFIGS, DEFAULT_CERT
from .examtopics_scraper import ExamTopicsScraper

__all__ = [
    'ExamTopicsScraper',
    'CERTIFICATION_CONFIGS',
    'DEFAULT_CERT'
]