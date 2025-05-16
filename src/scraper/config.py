#!/usr/bin/env python3
"""
Configuration for ExamTopics scraper
"""

# Certification configurations
CERTIFICATION_CONFIGS = {
    "terraform-associate": {
        "provider": "hashicorp",
        "display_name": "Terraform Associate",
        "url_pattern": r"https://www\.examtopics\.com/discussions/hashicorp/view/\d+-exam-terraform-associate-topic-(\d+)-question-(\d+)-discussion/",
        "target_url": "https://www.examtopics.com/exams/hashicorp/terraform-associate/view/",
        "discussion_url_pattern": "https://www.examtopics.com/discussions/hashicorp/view/{discussion_id}-exam-terraform-associate-topic-{topic}-question-{question}-discussion/",
    },
    "professional-machine-learning-engineer": {
        "provider": "google",
        "display_name": "Professional Machine Learning Engineer",
        "url_pattern": r"https://www\.examtopics\.com/discussions/google/view/\d+-exam-professional-machine-learning-engineer-topic-(\d+)-question-(\d+)-discussion/",
        "target_url": "https://www.examtopics.com/exams/google/professional-machine-learning-engineer/view/",
        "discussion_url_pattern": "https://www.examtopics.com/discussions/google/view/{discussion_id}-exam-professional-machine-learning-engineer-topic-{topic}-question-{question}-discussion/",
    },
    "az-900": {
        "provider": "microsoft",
        "display_name": "Microsoft Azure Fundamentals (AZ-900)",
        "url_pattern": r"https://www\.examtopics\.com/discussions/microsoft/view/\d+-exam-az-900-topic-(\d+)-question-(\d+)-discussion/",
        "target_url": "https://www.examtopics.com/exams/microsoft/az-900/view/",
        "discussion_url_pattern": "https://www.examtopics.com/discussions/microsoft/view/{discussion_id}-exam-az-900-topic-{topic}-question-{question}-discussion/",
    },
    "aws-certified-solutions-architect-associate-saa-c03": {
        "provider": "amazon",
        "display_name": "AWS Certified Solutions Architect Associate (SAA-C03)",
        "url_pattern": r"https://www\.examtopics\.com/discussions/amazon/view/\d+-exam-aws-certified-solutions-architect-associate-saa-c03-topic-(\d+)-question-(\d+)-discussion/",
        "target_url": "https://www.examtopics.com/exams/amazon/aws-certified-solutions-architect-associate-saa-c03/view/",
        "discussion_url_pattern": "https://www.examtopics.com/discussions/amazon/view/{discussion_id}-exam-aws-certified-solutions-architect-associate-saa-c03-topic-{topic}-question-{question}-discussion/",
    }
}

# Default certification
DEFAULT_CERT = "professional-machine-learning-engineer"

# Alternative search engines to bypass Google restrictions
SEARCH_ENGINES = [
    {"name": "Google", "url": "https://www.google.com/search?q={query}"},
    {"name": "Bing", "url": "https://www.bing.com/search?q={query}"},
    {"name": "DuckDuckGo", "url": "https://duckduckgo.com/?q={query}"},
    # {"name": "Yahoo", "url": "https://search.yahoo.com/search?p={query}"},
]
