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
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import urllib.parse

from playwright.async_api import async_playwright, Page, BrowserContext
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

# Configure rich console for output
console = Console()

# Target URL
TARGET_URL = "https://www.examtopics.com/exams/hashicorp/terraform-associate/view/"

# Alternative search engines to bypass Google restrictions
SEARCH_ENGINES = [
    {"name": "Google", "url": "https://www.google.com/search?q={query}"},
    # {"name": "Bing", "url": "https://www.bing.com/search?q={query}"},
    # {"name": "DuckDuckGo", "url": "https://duckduckgo.com/?q={query}"},
    # {"name": "Yahoo", "url": "https://search.yahoo.com/search?p={query}"},
]

# Output directory
OUTPUT_DIR = Path("data/terraform-associate")

# User agents to rotate
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_5_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36",
]

# Expected URL pattern for ExamTopics discussions
EXAMTOPICS_URL_PATTERN = r"https://www\.examtopics\.com/discussions/hashicorp/view/\d+-exam-terraform-associate-topic-(\d+)-question-(\d+)-discussion/"


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
        viewport={"width": 1920, "height": 1080},
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


def is_valid_examtopics_url(url: str, topic_number: int, question_number: int) -> bool:
    """
    Validate that the URL matches the expected ExamTopics URL pattern for the given topic and question.
    
    Args:
        url: The URL to validate
        topic_number: The expected topic number
        question_number: The expected question number
        
    Returns:
        True if the URL matches the expected pattern with correct topic and question numbers
    """
    # First check if it's an ExamTopics URL
    if "examtopics.com" not in url:
        return False
    
    # Match against the specific pattern
    match = re.search(EXAMTOPICS_URL_PATTERN, url)
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


async def search_and_find_link(query: str, topic_number: int, question_number: int) -> Optional[str]:
    """
    Search for a query using multiple search engines and find a link to ExamTopics.
    
    Args:
        query: The search query
        topic_number: The topic number to validate in the URL
        question_number: The question number to validate in the URL
        
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
                    
                    if href and is_valid_examtopics_url(href, topic_number, question_number):
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


async def scrape_exam_page(url: str) -> Dict[str, Any]:
    """
    Scrapes an exam page from ExamTopics and extracts the questions and answers.

    Args:
        url: The URL of the exam page to scrape

    Returns:
        Dictionary containing the extracted exam data
    """
    console.print(f"[bold blue]Scraping exam page:[/] {url}")

    # Create output directory if it doesn't exist
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    exam_data = {
        "title": "",
        "description": "",
        "questions": []
    }

    async with async_playwright() as p:
        # Setup browser with anti-detection measures
        context, page = await setup_browser_context(p)
        
        with console.status("[bold green]Loading page...") as status:
            await page.goto(url, wait_until="domcontentloaded")
            console.print("[green]✓[/] Page loaded")

        # Extract title and description
        exam_data["title"] = await page.title()
        
        # Extract exam description if available
        try:
            description_elem = await page.query_selector("div.exam-description")
            if description_elem:
                exam_data["description"] = await description_elem.text_content()
        except Exception as e:
            console.print(f"[yellow]Warning:[/] Could not extract description: {e}")

        # Extract questions
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("[bold blue]Extracting questions...", total=None)
            
            # Find all question elements
            question_elements = await page.query_selector_all("div.exam-question-card")
            
            for i, question_elem in enumerate(question_elements):
                try:
                    # Extract question number and text
                    question_header = await question_elem.query_selector("div.card-header")
                    question_number = await question_header.text_content() if question_header else f"Question {i+1}"
                    
                    # Extract question content
                    question_content = await question_elem.query_selector("div.question-body")
                    question_text = await question_content.inner_text() if question_content else "No content found"
                    
                    # Extract answer choices
                    answer_choices = []
                    choices_elements = await question_elem.query_selector_all("div.multi-choice-item")
                    for choice_elem in choices_elements:
                        choice_text = await choice_elem.inner_text()
                        # Clean up the choice text
                        choice_text = choice_text.strip()
                        answer_choices.append(choice_text)
                    
                    # Find discussion if available
                    discussion = ""
                    discussion_elem = await question_elem.query_selector("div.discussion-container")
                    if discussion_elem:
                        discussion = await discussion_elem.inner_text()
                    
                    # Create question object
                    question_data = {
                        "number": question_number.strip(),
                        "text": question_text.strip(),
                        "choices": answer_choices,
                        "discussion": discussion.strip() if discussion else ""
                    }
                    
                    exam_data["questions"].append(question_data)
                    progress.update(task, description=f"Extracted {len(exam_data['questions'])} questions")
                    
                except Exception as e:
                    console.print(f"[red]Error extracting question {i+1}:[/] {str(e)}")
            
        await context.close()
    
    # Save to JSON file
    output_file = OUTPUT_DIR / "terraform_associate_questions.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(exam_data, f, indent=2)
    
    console.print(f"[bold green]Successfully scraped and saved exam data to:[/] {output_file}")
    return exam_data


async def scrape_specific_questions(topic_number: int, start_question: int, end_question: int = None) -> List[Dict[str, Any]]:
    """
    Searches for specific exam questions and scrapes the details from ExamTopics.
    
    Args:
        topic_number: The topic number of the questions
        start_question: The starting question number to search for
        end_question: The ending question number (inclusive). If None, only scrapes the start_question
    
    Returns:
        List of dictionaries containing the extracted question data
    """
    # Create output directory if it doesn't exist
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # If end_question is not specified, only scrape the start_question
    if end_question is None:
        end_question = start_question
    
    results = []
    
    # Validate input
    if start_question > end_question:
        console.print("[red]Error:[/] start_question must be less than or equal to end_question")
        return results
    
    console.print(f"[bold blue]Scraping Terraform Associate Topic {topic_number} Questions {start_question} to {end_question}[/]")
    
    for question_number in range(start_question, end_question + 1):
        try:
            console.print(f"[bold cyan]Processing Question {question_number}...[/]")
            
            # Construct search query
            search_query = f"examtopics Exam Terraform Associate topic {topic_number} question {question_number} discussion"
            
            # Search for the link using our search engines
            examtopics_link = await search_and_find_link(search_query, topic_number, question_number)
            
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
            output_file = OUTPUT_DIR / f"terraform_associate_topic{topic_number}_q{question_number}.json"
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
    combined_output_file = OUTPUT_DIR / f"terraform_associate_topic{topic_number}_q{start_question}-q{end_question}.json"
    with open(combined_output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    
    console.print(f"[bold green]Successfully scraped and saved {len(results)} questions to:[/] {combined_output_file}")
    return results


async def main():
    """Main entry point for the scraper"""
    console.print("[bold]===== ExamTopics Terraform Associate Scraper =====")
    
    # Run the improved function to scrape a range of questions
    await scrape_specific_questions(1, 32, 33)  # Topic 1, Questions 32 to 33


if __name__ == "__main__":
    asyncio.run(main())