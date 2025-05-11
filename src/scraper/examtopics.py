#!/usr/bin/env python3
"""
ExamTopics Scraper

This module scrapes exam questions from ExamTopics website for certification preparation.
"""

import asyncio
import re
import json
import os
import random
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import urllib.parse

from playwright.async_api import async_playwright, Page, BrowserContext
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

# Configure rich console for output
console = Console()

# Certification configurations
CERTIFICATION_CONFIGS = {
    "terraform-associate": {
        "provider": "hashicorp",
        "display_name": "Terraform Associate",
        "url_pattern": r"https://www\.examtopics\.com/discussions/hashicorp/view/\d+-exam-terraform-associate-topic-(\d+)-question-(\d+)-discussion/",
        "target_url": "https://www.examtopics.com/exams/hashicorp/terraform-associate/view/"
    },
    "professional-machine-learning-engineer": {
        "provider": "google",
        "display_name": "Professional Machine Learning Engineer",
        "url_pattern": r"https://www\.examtopics\.com/discussions/google/view/\d+-exam-professional-machine-learning-engineer-topic-(\d+)-question-(\d+)-discussion/",
        "target_url": "https://www.examtopics.com/exams/google/professional-machine-learning-engineer/view/"
    }
}

# Default certification
DEFAULT_CERT = "professional-machine-learning-engineer"

# Alternative search engines to bypass Google restrictions
SEARCH_ENGINES = [
    {"name": "Google", "url": "https://www.google.com/search?q={query}"},
    # {"name": "Bing", "url": "https://www.bing.com/search?q={query}"},
    # {"name": "DuckDuckGo", "url": "https://duckduckgo.com/?q={query}"},
    # {"name": "Yahoo", "url": "https://search.yahoo.com/search?p={query}"},
]

# User agents to rotate
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    # "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
    # "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_5_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36",
]


async def setup_browser_context(playwright) -> Tuple[BrowserContext, Page]:
    """
    Set up a browser context with configurations to avoid detection.
    
    Args:
        playwright: The playwright instance
    
    Returns:
        Tuple of browser context and page
    """
    # Use a random user agent
    user_agent = random.choice(USER_AGENTS)
    print(f"[bold green]Using User-Agent:[/] {user_agent}")
    # Set up the browser with specific configurations to avoid detection
    browser = await playwright.chromium.launch(
        headless=False,  # Set to True in production for better performance
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            "--window-position=0,0",
            "--ignore-certifcate-errors",
            "--ignore-certifcate-errors-spki-list",
            "--disable-dev-shm-usage",
        ]
    )
    
    # Create a context with specific device settings
    context = await browser.new_context(
        user_agent=user_agent,
        viewport={"width": 950, "height": 1080},
        locale="en-US",
        timezone_id="America/New_York",
        permissions=["geolocation"],
        geolocation={"latitude": random.uniform(38.0, 42.0), "longitude": random.uniform(-75.0, -71.0)},  # Random US East Coast location
    )
    
    # Add additional headers
    await context.set_extra_http_headers({
        "Accept-Language": "en-US,en;q=0.9",
    })
    
    # Create a page from the context
    page = await context.new_page()
    
    # Emulate human-like behavior by setting page properties
    await page.evaluate("""() => {
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { 
            get: () => [1, 2, 3, 4, 5] 
        });
    }""")
    
    return context, page


def is_valid_examtopics_url(url: str, topic_number: int, question_number: int, url_pattern: str) -> bool:
    """
    Validate that the URL matches the expected ExamTopics URL pattern for the given topic and question.
    
    Args:
        url: The URL to validate
        topic_number: The expected topic number
        question_number: The expected question number
        url_pattern: The regex pattern to match against
        
    Returns:
        True if the URL matches the expected pattern with correct topic and question numbers
    """
    # First check if it's an ExamTopics URL
    if "examtopics.com" not in url:
        return False
    
    # Match against the specific pattern
    match = re.search(url_pattern, url)
    if match:
        # Extract topic and question numbers from the URL
        url_topic = int(match.group(1))
        url_question = int(match.group(2))
        
        # Verify that they match the expected values
        return url_topic == topic_number and url_question == question_number
    
    # Accept other ExamTopics URLs that contain the topic and question numbers
    # This is a fallback for when the URL doesn't match our primary pattern
    if (f"topic-{topic_number}" in url or f"topic{topic_number}" in url) and \
       (f"question-{question_number}" in url or f"question{question_number}" in url):
        return True
    
    return False


async def search_and_find_link(query: str, topic_number: int, question_number: int, url_pattern: str) -> Optional[str]:
    """
    Search for a query using multiple search engines and find a link to ExamTopics.
    
    Args:
        query: The search query
        topic_number: The topic number to validate in the URL
        question_number: The question number to validate in the URL
        url_pattern: The regex pattern to match against
        
    Returns:
        The URL to the ExamTopics page or None if not found
    """
    # Try each search engine in order until we find a result
    for engine in SEARCH_ENGINES:
        console.print(f"[bold cyan]Searching with {engine['name']}...[/]")
        
        search_url = engine["url"].format(query=urllib.parse.quote(query))
        
        async with async_playwright() as p:
            try:
                # Setup browser with anti-detection measures
                context, page = await setup_browser_context(p)
                
                # Navigate to the search engine
                await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                
                # Check if we need to solve a captcha
                if await check_and_solve_captcha(page):
                    console.print(f"[yellow]Captcha detected on {engine['name']}. Attempting to solve...[/]")
                    
                    # If we can't solve the captcha automatically, wait for user input
                    console.print("[bold yellow]Please solve the captcha in the browser window and press Enter when done.[/]")
                    input()
                
                # Simulate human-like scrolling and waiting
                await human_like_scroll(page)
                
                # Add a random delay to mimic human behavior
                await asyncio.sleep(random.uniform(2, 5))
                
                # Find all search result links
                all_links = await page.query_selector_all("a")
                
                for link in all_links:
                    href = await link.get_attribute("href")
                    
                    if href and is_valid_examtopics_url(href, topic_number, question_number, url_pattern):
                        console.print(f"[green]Found valid ExamTopics link via {engine['name']}![/]")
                        await context.close()
                        return href
                    elif href and "examtopics.com" in href:
                        # Log but don't return non-matching ExamTopics URLs
                        console.print(f"[yellow]Found ExamTopics link that doesn't match expected format: {href}[/]")
                
                # If we get here, we couldn't find a valid link with this search engine
                console.print(f"[yellow]No valid ExamTopics link found with {engine['name']}[/]")
                await context.close()
                
            except Exception as e:
                console.print(f"[red]Error with {engine['name']} search:[/] {str(e)}")
                continue
    
    # If we've tried all search engines and failed, return None
    console.print("[yellow]Could not find valid ExamTopics link via any search engine.[/]")
    return None


async def check_and_solve_captcha(page: Page) -> bool:
    """
    Check if a captcha is present and attempt to solve it.
    
    Args:
        page: The Playwright page
    
    Returns:
        True if captcha was detected, False otherwise
    """
    # Common captcha indicators
    captcha_indicators = [
        "captcha",
        "robot",
        "verify you're a human",
        "security check",
        "unusual traffic",
        "recaptcha",
    ]
    
    # Check page content for captcha indicators
    content = await page.content()
    content_lower = content.lower()
    
    for indicator in captcha_indicators:
        if indicator in content_lower:
            return True
    
    # Check for specific captcha elements
    captcha_selectors = [
        "iframe[src*='recaptcha']",
        "iframe[src*='captcha']",
        "div.g-recaptcha",
        "form#captcha",
    ]
    
    for selector in captcha_selectors:
        element = await page.query_selector(selector)
        if element:
            return True
    
    return False


async def human_like_scroll(page: Page):
    """
    Simulates human-like scrolling behavior on a page.
    
    Args:
        page: The Playwright page
    """
    # Get page height
    height = await page.evaluate("document.body.scrollHeight")
    
    # Scroll down in a human-like way with variable speed
    viewport_height = await page.evaluate("window.innerHeight")
    current_position = 0
    
    while current_position < height:
        # Calculate a random scroll amount
        scroll_amount = random.randint(100, 500)
        current_position += scroll_amount
        
        # Scroll to the new position
        await page.evaluate(f"window.scrollTo(0, {current_position})")
        
        # Add a random delay between scrolls
        await asyncio.sleep(random.uniform(0.2, 1.0))


async def scrape_exam_views(certification: str, view_numbers: List[int]) -> Dict[str, Any]:
    """
    Scrapes exam views (pages with 10 questions each) from ExamTopics.
    
    Args:
        certification: The certification key from CERTIFICATION_CONFIGS
        view_numbers: List of view numbers to scrape (1, 2, etc.)
        
    Returns:
        Dictionary containing the extracted exam data from all views
    """
    config = CERTIFICATION_CONFIGS[certification]
    output_dir = Path(f"data/{certification}")
    provider = config["provider"]
    display_name = config["display_name"]
    
    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    
    all_questions = []
    total_questions_count = 0
    exam_data = {
        "title": f"{display_name} Exam Questions",
        "description": f"Scraped from ExamTopics",
        "questions": []
    }
    
    for view_number in view_numbers:
        # Construct the URL for this view
        view_url = f"{config['target_url']}{view_number}/"
        console.print(f"[bold blue]Scraping {display_name} exam view #{view_number}:[/] {view_url}")
        
        async with async_playwright() as p:
            # Setup browser with anti-detection measures
            context, page = await setup_browser_context(p)
            
            with console.status(f"[bold green]Loading exam view page {view_number}...") as status:
                try:
                    await page.goto(view_url, wait_until="domcontentloaded", timeout=120000)
                    console.print(f"[green]✓[/] View {view_number} page loaded")
                    
                    # Check if we need to solve a captcha
                    if await check_and_solve_captcha(page):
                        console.print(f"[yellow]Captcha detected. Waiting for manual solving...[/]")
                        console.print("[bold yellow]Please solve the captcha in the browser window and press Enter when done.[/]")
                        input()
                except Exception as e:
                    console.print(f"[red]Error loading view {view_number}: {str(e)}[/]")
                    await context.close()
                    continue
            
            # Extract total questions count if first view
            if view_number == 1:
                try:
                    # Try to find the element that contains the total questions count
                    questions_info = await page.query_selector(".examQa__item:nth-child(4)")
                    if questions_info:
                        text = await questions_info.inner_text()
                        # Extract the number from text like "Exam Questions: 358"
                        match = re.search(r"Questions:\s*(\d+)", text)
                        if match:
                            total_questions_count = int(match.group(1))
                            console.print(f"[blue]Total questions for this exam: {total_questions_count}[/]")
                except Exception as e:
                    console.print(f"[yellow]Could not extract total questions count: {e}[/]")
            
            # Find all question elements
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task(f"[bold blue]Extracting questions from view {view_number}...", total=None)
                
                # Query for all question cards
                question_elements = await page.query_selector_all("div.exam-question-card")
                
                progress.update(task, total=len(question_elements))
                progress.start_task(task)
                
                for i, question_elem in enumerate(question_elements):
                    try:
                        # Extract question number, topic, and text
                        question_header = await question_elem.query_selector("div.card-header")
                        question_full_number = await question_header.inner_text() if question_header else f"Question #{i+1}"
                        
                        # Parse question number from format like "Question #1"
                        question_number_match = re.search(r"Question #(\d+)", question_full_number)
                        question_number = int(question_number_match.group(1)) if question_number_match else (i + 1)
                        
                        # Extract topic
                        topic_span = await question_elem.query_selector(".question-title-topic")
                        topic = await topic_span.inner_text() if topic_span else "Unknown Topic"
                        
                        # Extract question body
                        question_body = await question_elem.query_selector("div.question-body")
                        question_id = await question_body.get_attribute("data-id") if question_body else None
                        
                        # Extract question text
                        question_text_elem = await question_body.query_selector("p.card-text")
                        question_text = await question_text_elem.inner_html() if question_text_elem else "No content found"
                        # Clean up the question text
                        question_text = question_text.strip()
                        
                        # Extract choices
                        choices = []
                        choices_container = await question_elem.query_selector("div.question-choices-container")
                        if choices_container:
                            choice_items = await choices_container.query_selector_all("li.multi-choice-item")
                            
                            for choice_item in choice_items:
                                # Get letter (A, B, C, etc.)
                                letter_elem = await choice_item.query_selector("span.multi-choice-letter")
                                letter = await letter_elem.inner_text() if letter_elem else ""
                                letter = letter.strip().replace(".", "")
                                
                                # Get full choice text
                                choice_text = await choice_item.inner_text()
                                # Remove the letter part from the text
                                choice_text = choice_text.replace(f"{letter}.", "").strip()
                                
                                # Check if this choice is marked as correct
                                is_correct = "correct-hidden" in (await choice_item.get_attribute("class") or "")
                                
                                choices.append({
                                    "letter": letter,
                                    "text": choice_text,
                                    "is_correct": is_correct
                                })
                        
                        # Get correct answer
                        correct_answer = ""
                        correct_answer_elem = await question_elem.query_selector("span.correct-answer")
                        if correct_answer_elem:
                            # Click on reveal solution if it exists
                            reveal_btn = await question_elem.query_selector("a.reveal-solution")
                            if reveal_btn:
                                await reveal_btn.click()
                                await asyncio.sleep(0.5)
                                # Try to get the answer again after revealing it
                                correct_answer_elem = await question_elem.query_selector("span.correct-answer")
                            
                            if correct_answer_elem:
                                correct_answer = await correct_answer_elem.inner_text()
                                correct_answer = correct_answer.strip()
                        
                        # Community votes data
                        votes_data = []
                        try:
                            votes_script = await question_elem.query_selector(f"script#${question_id}")
                            if votes_script:
                                votes_json = await votes_script.inner_text()
                                votes_data = json.loads(votes_json)
                        except Exception as e:
                            console.print(f"[yellow]Error parsing votes data: {e}[/]")
                        
                        # Create question object
                        question_data = {
                            "question_id": question_id,
                            "question_number": question_number,
                            "view_number": view_number,
                            "topic": topic,
                            "text": question_text,
                            "choices": choices,
                            "correct_answer": correct_answer,
                            "community_votes": votes_data
                        }
                        
                        exam_data["questions"].append(question_data)
                        progress.update(task, advance=1)
                        
                    except Exception as e:
                        console.print(f"[red]Error extracting question {i+1} in view {view_number}:[/] {str(e)}")
            
            await context.close()
            
            # Add a delay between views to prevent blocking
            if view_number < view_numbers[-1]:
                delay = random.uniform(5, 10)
                console.print(f"[cyan]Waiting {delay:.1f} seconds before processing next view...[/]")
                await asyncio.sleep(delay)
    
    # Calculate a completion percentage
    if total_questions_count > 0:
        completion_percentage = (len(exam_data["questions"]) / total_questions_count) * 100
        console.print(f"[green]Scraped {len(exam_data['questions'])} questions out of {total_questions_count} ({completion_percentage:.1f}%)[/]")
    
    # Save to JSON file
    output_file = output_dir / f"{certification}_questions_views.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(exam_data, f, indent=2)
    
    console.print(f"[bold green]Successfully scraped and saved exam view data to:[/] {output_file}")
    return exam_data


async def scrape_specific_questions(certification: str, topic_number: int, start_question: int, end_question: int = None) -> List[Dict[str, Any]]:
    """
    Searches for specific exam questions and scrapes the details from ExamTopics.
    
    Args:
        certification: The certification key from CERTIFICATION_CONFIGS
        topic_number: The topic number of the questions
        start_question: The starting question number to search for
        end_question: The ending question number (inclusive). If None, only scrapes the start_question
    
    Returns:
        List of dictionaries containing the extracted question data
    """
    config = CERTIFICATION_CONFIGS[certification]
    output_dir = Path(f"data/{certification}")
    url_pattern = config["url_pattern"]
    display_name = config["display_name"]
    provider = config["provider"]
    
    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # If end_question is not specified, only scrape the start_question
    if end_question is None:
        end_question = start_question
    
    results = []
    
    # Validate input
    if start_question > end_question:
        console.print("[red]Error:[/] start_question must be less than or equal to end_question")
        return results
    
    console.print(f"[bold blue]Scraping {display_name} Topic {topic_number} Questions {start_question} to {end_question}[/]")
    
    for question_number in range(start_question, end_question + 1):
        try:
            console.print(f"[bold cyan]Processing Question {question_number}...[/]")
            
            # Construct search query
            search_query = f"examtopics {provider} {display_name} topic {topic_number} question {question_number} discussion"
            
            # Search for the link using our search engines
            examtopics_link = await search_and_find_link(search_query, topic_number, question_number, url_pattern)
            
            # If we couldn't find the link, skip this question
            if not examtopics_link:
                console.print(f"[red]Error:[/] Could not find ExamTopics link for Topic {topic_number} Question {question_number}")
                continue
            
            question_data = {
                "topic_number": topic_number,
                "question_number": question_number,
                "question_text": "",
                "choices": [],
                "suggested_answer": "",
                "top_voted_comments": []
            }
            
            # Now scrape the question page
            async with async_playwright() as p:
                # Setup browser with anti-detection measures
                context, page = await setup_browser_context(p)
                
                # Navigate to the ExamTopics page
                with console.status(f"[bold green]Loading ExamTopics page for Topic {topic_number} Question {question_number}...") as status:
                    await page.goto(examtopics_link, wait_until="domcontentloaded", timeout=60000)
                    
                    # Add random wait time to mimic human behavior
                    await asyncio.sleep(random.uniform(2, 5))
                    
                    console.print("[green]✓[/] ExamTopics page loaded")
                
                try:
                    # Extract question details
                    # Question text
                    question_body_elem = await page.query_selector("div.question-body")
                    if question_body_elem:
                        # Extract the question text paragraph
                        question_text_elem = await question_body_elem.query_selector("p.card-text")
                        if question_text_elem:
                            question_data["question_text"] = (await question_text_elem.inner_text()).strip()
                    
                    # Extract answer choices
                    choices_elements = await page.query_selector_all("li.multi-choice-item")
                    for choice_elem in choices_elements:
                        choice_letter_elem = await choice_elem.query_selector("span.multi-choice-letter")
                        choice_letter = ""
                        if choice_letter_elem:
                            choice_letter_text = await choice_letter_elem.inner_text()
                            choice_letter = choice_letter_text.strip().replace(".", "")
                        
                        choice_text = await choice_elem.inner_text()
                        # Remove the choice letter part from the text
                        if choice_letter:
                            choice_text = choice_text.replace(f"{choice_letter}.", "").strip()
                        
                        question_data["choices"].append({
                            "letter": choice_letter,
                            "text": choice_text
                        })
                    
                    # Sometimes the suggested answer might be hidden behind a button
                    reveal_btn = await page.query_selector("a.reveal-solution")
                    if reveal_btn:
                        await reveal_btn.click()
                        # Wait for the answer to appear
                        await asyncio.sleep(1)
                    
                    # Extract suggested answer
                    correct_answer_box = await page.query_selector("span.correct-answer")
                    if correct_answer_box:
                        question_data["suggested_answer"] = (await correct_answer_box.inner_text()).strip()
                    
                    # Extract top voted comments
                    comments = await page.query_selector_all("div.comment-container")
                    
                    for comment in comments[:5]:  # Get top 5 comments
                        try:
                            # Check if it's a highly voted comment
                            badge = await comment.query_selector("span.badge")
                            is_highly_voted = badge and "Highly Voted" in await badge.inner_text()
                            
                            # Get comment username
                            username_elem = await comment.query_selector("h5.comment-username")
                            username = await username_elem.inner_text() if username_elem else "Unknown"
                            
                            # Get comment content
                            content_elem = await comment.query_selector("div.comment-content")
                            content = await content_elem.inner_text() if content_elem else ""
                            
                            # Get upvote count
                            upvote_elem = await comment.query_selector("span.upvote-count")
                            upvote_count = 0
                            if upvote_elem:
                                upvote_text = await upvote_elem.inner_text()
                                try:
                                    upvote_count = int(upvote_text)
                                except ValueError:
                                    upvote_count = 0
                            
                            # Get selected answer if any
                            selected_answer_elem = await comment.query_selector("div.comment-selected-answers")
                            selected_answer = ""
                            if selected_answer_elem:
                                selected_answer_text = await selected_answer_elem.inner_text()
                                selected_answer = selected_answer_text.replace("Selected Answer:", "").strip()
                            
                            comment_data = {
                                "username": username.strip(),
                                "content": content.strip(),
                                "upvotes": upvote_count,
                                "is_highly_voted": is_highly_voted,
                                "selected_answer": selected_answer
                            }
                            
                            question_data["top_voted_comments"].append(comment_data)
                        except Exception as e:
                            console.print(f"[yellow]Warning:[/] Error extracting comment: {str(e)}")
                    
                    # Sort comments by upvotes in descending order
                    question_data["top_voted_comments"].sort(key=lambda x: x["upvotes"], reverse=True)
                    
                except Exception as e:
                    console.print(f"[red]Error during scraping for question {question_number}:[/] {str(e)}")
                finally:
                    await context.close()
            
            # Save to JSON file
            output_file = output_dir / f"{certification}_topic{topic_number}_q{question_number}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(question_data, f, indent=2)
            
            console.print(f"[bold green]Successfully scraped and saved question data to:[/] {output_file}")
            
            # Add to results list
            results.append(question_data)
            
            # Add a delay between requests to avoid overwhelming servers
            # Use a longer, random delay to mimic human behavior
            delay = random.uniform(10, 15)
            console.print(f"[cyan]Waiting {delay:.1f} seconds before processing next question...[/]")
            await asyncio.sleep(delay)
            
        except Exception as e:
            console.print(f"[red]Failed to scrape question {question_number}:[/] {str(e)}")
    
    # Save the combined results
    combined_output_file = output_dir / f"{certification}_topic{topic_number}_q{start_question}-q{end_question}.json"
    with open(combined_output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    
    console.print(f"[bold green]Successfully scraped and saved {len(results)} questions to:[/] {combined_output_file}")
    return results


async def main():
    """Main entry point for the scraper"""
    parser = argparse.ArgumentParser(description='ExamTopics Scraper')
    parser.add_argument('--certification', type=str, default=DEFAULT_CERT,
                        choices=list(CERTIFICATION_CONFIGS.keys()),
                        help='Certification to scrape')
    parser.add_argument('--mode', type=str, choices=['views', 'search', 'both'], default='both',
                        help='Scraping mode: views (scrape view pages), search (scrape specific questions), or both')
    parser.add_argument('--views', type=str, default='1,2',
                        help='Comma-separated list of view numbers to scrape (e.g., "1,2,3")')
    parser.add_argument('--topic', type=int, default=1,
                        help='Topic number to scrape (for search mode)')
    parser.add_argument('--start', type=int, default=1,
                        help='Starting question number (for search mode)')
    parser.add_argument('--end', type=int, default=None,
                        help='Ending question number (inclusive, for search mode)')
    
    args = parser.parse_args()
    certification = args.certification
    config = CERTIFICATION_CONFIGS[certification]
    
    console.print(f"[bold]===== ExamTopics {config['display_name']} Scraper =====")
    
    # Parse view numbers
    view_numbers = [int(v.strip()) for v in args.views.split(',')]
    
    # Run the appropriate scraper mode(s)
    if args.mode in ['views', 'both']:
        console.print(f"[bold green]Starting views scraping mode for views: {view_numbers}[/]")
        await scrape_exam_views(certification, view_numbers)
    
    if args.mode in ['search', 'both']:
        console.print(f"[bold green]Starting search scraping mode for questions {args.start} to {args.end or args.start}[/]")
        await scrape_specific_questions(certification, args.topic, args.start, args.end)


if __name__ == "__main__":
    asyncio.run(main())