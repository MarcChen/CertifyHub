#!/usr/bin/env python3
"""
Search scraper for ExamTopics

This module handles scraping individual exam questions via search engines.
"""

import asyncio
import json
import re
import random
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Optional, List, Set
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page
from rich.console import Console

from .browser_utils import (
    setup_browser_context,
    check_and_solve_captcha,
    human_like_scroll,
    handle_captcha_automatically,
    rotate_browser_context,
    extract_content_behind_paywall
)
from .config import SEARCH_ENGINES

console = Console()


def is_valid_examtopics_url(
    url: str, 
    topic_number: int, 
    question_number: int, 
    url_pattern: str
) -> bool:
    """
    Validate that the URL matches the expected ExamTopics URL pattern.
    
    Args:
        url: The URL to validate
        topic_number: The expected topic number
        question_number: The expected question number
        url_pattern: The regex pattern to match against
        
    Returns:
        True if the URL matches the expected pattern
    """
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
    if (f"topic-{topic_number}" in url or f"topic{topic_number}" in url) and \
       (f"question-{question_number}" in url or f"question{question_number}" in url):
        return True
    
    return False


async def search_for_question_url(
    provider: str,
    certification: str,
    topic_number: int,
    question_number: int,
    url_pattern: str,
    max_attempts: int = 3
) -> Optional[str]:
    """
    Search for a question using search engines.
    
    Args:
        provider: The provider (e.g., "google")
        certification: The certification name
        topic_number: The topic number
        question_number: The question number
        url_pattern: The regex pattern to match URLs against
        max_attempts: Maximum number of search attempts
        
    Returns:
        URL to the question page or None if not found
    """
    # Construct search query
    query = f"examtopics {provider} {certification} topic {topic_number} question {question_number} discussion"
    encoded_query = urllib.parse.quote(query)
    
    # Try different search engines
    for engine in SEARCH_ENGINES:
        console.print(f"[bold cyan]Searching with {engine['name']} for question {question_number}...[/]")
        
        search_url = engine["url"].format(query=encoded_query)
        
        # Make multiple attempts
        for attempt in range(max_attempts):
            console.print(f"[cyan]Search attempt {attempt + 1}/{max_attempts} with {engine['name']}[/]")
            
            async with async_playwright() as p:
                try:
                    # Setup browser with anti-detection measures
                    context, page = await rotate_browser_context(p)
                    if not context or not page:
                        console.print(f"[red]Failed to create browser context. Trying again...[/]")
                        continue
                    
                    # Navigate to the search engine
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                    
                    # Check for captcha and try to solve automatically
                    if await check_and_solve_captcha(page):
                        console.print(f"[yellow]Captcha detected on {engine['name']}. Attempting to solve...[/]")
                        if not await handle_captcha_automatically(page):
                            # If automatic bypass failed, try a different approach
                            console.print(f"[yellow]Automatic captcha bypass failed. Trying different approach...[/]")
                            await context.close()
                            continue
                    
                    # Wait for search results to load
                    await page.wait_for_selector("a", timeout=10000)
                    
                    # Simulate human-like scrolling
                    await human_like_scroll(page)
                    
                    # Add a random delay to mimic human behavior
                    await asyncio.sleep(random.uniform(1, 3))
                    
                    # Find all links
                    all_links = await page.query_selector_all("a")
                    
                    for link in all_links:
                        href = await link.get_attribute("href")
                        
                        if href and is_valid_examtopics_url(href, topic_number, question_number, url_pattern):
                            console.print(f"[green]Found valid ExamTopics link: {href}[/]")
                            await context.close()
                            return href
                        elif href and "examtopics.com" in href and "discussion" in href:
                            console.print(f"[yellow]Found potential ExamTopics link: {href}[/]")
                            # Check if it might be the right URL even if it doesn't match our exact pattern
                            if f"question-{question_number}" in href or f"question{question_number}" in href:
                                console.print(f"[green]Link contains question number {question_number}, accepting it[/]")
                                await context.close()
                                return href
                    
                    console.print(f"[yellow]No valid ExamTopics link found with {engine['name']} (attempt {attempt + 1})[/]")
                    
                    # Try clicking "Next" if we didn't find anything on the first page
                    if attempt == 0:
                        next_page_selectors = ["#pnnext", "a:has-text('Next')", "a.next", "a[aria-label='Next']"]
                        for selector in next_page_selectors:
                            next_button = await page.query_selector(selector)
                            if next_button:
                                console.print(f"[cyan]Trying next page of search results...[/]")
                                await next_button.click()
                                await page.wait_for_load_state("domcontentloaded")
                                await asyncio.sleep(2)
                                
                                # Check for new links on the next page
                                new_links = await page.query_selector_all("a")
                                for link in new_links:
                                    href = await link.get_attribute("href")
                                    if href and is_valid_examtopics_url(href, topic_number, question_number, url_pattern):
                                        console.print(f"[green]Found valid ExamTopics link on next page: {href}[/]")
                                        await context.close()
                                        return href
                                break
                    
                    await context.close()
                    
                except Exception as e:
                    console.print(f"[red]Error with {engine['name']} search:[/] {str(e)}")
                    if 'context' in locals():
                        await context.close()
                    
                # Wait before the next attempt
                await asyncio.sleep(random.uniform(3, 7))
    
    # Construct a direct URL guess as a last resort
    direct_url = f"https://www.examtopics.com/discussions/{provider}/view/1-exam-{certification}-topic-{topic_number}-question-{question_number}-discussion/"
    console.print(f"[yellow]Could not find URL via search. Trying direct URL: {direct_url}[/]")
    
    return direct_url


async def extract_question_from_discussion_page(page: Page) -> Dict[str, Any]:
    """
    Extract question data from a discussion page.
    
    Args:
        page: The Playwright page with the discussion
        
    Returns:
        Dictionary with the extracted question data
    """
    question_data = {
        "question_number": 0,
        "topic_number": 0,
        "question_text": "",
        "choices": [],
        "correct_answer": "",
        "explanation": "",
        "top_voted_comments": []
    }
    
    try:
        # Extract question details
        
        # First try to get the question number and topic from the URL or title
        url = page.url
        title = await page.title()
        
        # Try to extract topic and question number from URL
        url_match = re.search(r"topic-(\d+)-question-(\d+)", url)
        if url_match:
            question_data["topic_number"] = int(url_match.group(1))
            question_data["question_number"] = int(url_match.group(2))
        else:
            # Try to extract from title
            title_match = re.search(r"Topic (\d+) Question (\d+)", title)
            if title_match:
                question_data["topic_number"] = int(title_match.group(1))
                question_data["question_number"] = int(title_match.group(2))
        
        # Question text
        question_body_elem = await page.query_selector("div.question-body")
        if question_body_elem:
            # Extract the question text paragraph
            question_text_elem = await question_body_elem.query_selector("p.card-text")
            if question_text_elem:
                question_data["question_text"] = (await question_text_elem.inner_text()).strip()
            else:
                # Try with different selector
                question_data["question_text"] = (await question_body_elem.inner_text()).strip()
        
        # Extract answer choices
        choices_container = await page.query_selector("div.question-choices-container")
        if choices_container:
            choice_items = await choices_container.query_selector_all("li.multi-choice-item")
            
            for choice_item in choice_items:
                # Get letter (A, B, C, etc.)
                letter_elem = await choice_item.query_selector("span.multi-choice-letter")
                letter = ""
                if letter_elem:
                    letter_text = await letter_elem.inner_text()
                    letter = letter_text.strip().replace(".", "")
                
                # Get full choice text
                choice_text = await choice_item.inner_text()
                # Remove the letter part from the text
                if letter:
                    choice_text = choice_text.replace(f"{letter}.", "").strip()
                
                # Check if this choice is marked as correct
                is_correct = "correct-hidden" in (await choice_item.get_attribute("class") or "")
                
                choice = {
                    "letter": letter,
                    "text": choice_text,
                    "is_correct": is_correct
                }
                
                question_data["choices"].append(choice)
                
                # If this choice is marked as correct, add it to correct_answer
                if is_correct:
                    question_data["correct_answer"] = letter
        
        # Sometimes the suggested answer might be hidden behind a button
        if not question_data["correct_answer"]:
            reveal_btn = await page.query_selector("a.reveal-solution")
            if reveal_btn:
                try:
                    await reveal_btn.click()
                    # Wait for the answer to appear
                    await asyncio.sleep(1)
                except Exception:
                    pass
            
            # Extract suggested answer
            correct_answer_box = await page.query_selector("span.correct-answer")
            if correct_answer_box:
                question_data["correct_answer"] = (await correct_answer_box.inner_text()).strip()
        
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
                console.print(f"[yellow]Warning: Error extracting comment: {str(e)}[/]")
        
        # Sort comments by upvotes in descending order
        question_data["top_voted_comments"].sort(key=lambda x: x["upvotes"], reverse=True)
        
        # Try to extract explanation
        explanation_elem = await page.query_selector("div.question-explanation")
        if explanation_elem:
            question_data["explanation"] = (await explanation_elem.inner_text()).strip()
        elif question_data["top_voted_comments"]:
            # Use the top voted comment as explanation if no official one exists
            question_data["explanation"] = question_data["top_voted_comments"][0]["content"]
    
    except Exception as e:
        console.print(f"[red]Error extracting question data from discussion page: {str(e)}[/]")
    
    return question_data


async def get_question_via_search(
    certification: str,
    topic_number: int,
    question_number: int,
    provider: str,
    display_name: str,
    url_pattern: str,
    max_retries: int = 3
) -> Optional[Dict[str, Any]]:
    """
    Search for and scrape a specific exam question.
    
    Args:
        certification: The certification key (e.g., "professional-machine-learning-engineer")
        topic_number: The topic number
        question_number: The question number to search for
        provider: The provider (e.g., "google")
        display_name: Display name of the certification
        url_pattern: The regex pattern for valid URLs
        max_retries: Maximum number of retries
        
    Returns:
        Dictionary containing the question data or None if failed
    """
    console.print(f"[bold blue]Searching for {display_name} Topic {topic_number} Question {question_number}[/]")
    
    # Search for the question URL
    url = await search_for_question_url(
        provider,
        certification,
        topic_number,
        question_number,
        url_pattern
    )
    
    if not url:
        console.print(f"[red]Could not find URL for question {question_number}[/]")
        return None
    
    # Now scrape the question page
    output_dir = Path(f"data/{certification}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    retry_count = 0
    question_data = None
    
    while retry_count < max_retries and not question_data:
        async with async_playwright() as p:
            try:
                # Setup browser with anti-detection measures
                context, page = await rotate_browser_context(p)
                if not context or not page:
                    console.print(f"[red]Failed to create browser context. Retrying...[/]")
                    retry_count += 1
                    continue
                
                # Navigate to the question page
                console.print(f"[cyan]Loading question page: {url}[/]")
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Check for captcha
                if await check_and_solve_captcha(page):
                    console.print("[yellow]Captcha detected on question page. Attempting to bypass...[/]")
                    if not await handle_captcha_automatically(page):
                        console.print("[yellow]Automatic captcha bypass failed. Retrying with fresh browser...[/]")
                        await context.close()
                        retry_count += 1
                        continue
                
                # Check for paywall or premium content
                content = await page.content()
                if "premium" in content.lower() or "subscribe" in content.lower() or "paywall" in content.lower():
                    console.print(f"[yellow]Detected paywall/premium content for question {question_number}[/]")
                    
                    # Try to extract content from behind the paywall
                    await extract_content_behind_paywall(page)
                
                # Extract the question data
                question_data = await extract_question_from_discussion_page(page)
                
                # Validate the extracted data
                if not question_data["question_text"]:
                    console.print(f"[yellow]Failed to extract question text for question {question_number}[/]")
                    question_data = None
                    retry_count += 1
                    await context.close()
                    continue
                
                # Set proper question number and topic if not extracted from URL
                if question_data["question_number"] == 0:
                    question_data["question_number"] = question_number
                if question_data["topic_number"] == 0:
                    question_data["topic_number"] = topic_number
                
                # Save the data to file
                output_file = output_dir / f"{certification}_topic{topic_number}_q{question_number}.json"
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(question_data, f, indent=2)
                
                console.print(f"[green]Successfully scraped and saved question {question_number}[/]")
                
                await context.close()
                
            except Exception as e:
                console.print(f"[red]Error scraping question {question_number} (attempt {retry_count + 1}): {str(e)}[/]")
                if 'context' in locals():
                    await context.close()
                retry_count += 1
                
                # Wait before retrying
                delay = random.uniform(5, 10)
                console.print(f"[cyan]Waiting {delay:.1f} seconds before retry...[/]")
                await asyncio.sleep(delay)
    
    return question_data


async def scrape_questions_from_list(
    certification: str,
    topic_number: int,
    question_numbers: List[int],
    provider: str,
    display_name: str,
    url_pattern: str,
    batch_size: int = 3
) -> List[Dict[str, Any]]:
    """
    Scrape multiple questions by their numbers.
    
    Args:
        certification: The certification key
        topic_number: The topic number
        question_numbers: List of question numbers to scrape
        provider: The provider name
        display_name: Display name of the certification
        url_pattern: The regex pattern for URLs
        batch_size: Number of questions to process in parallel
        
    Returns:
        List of question data dictionaries
    """
    results = []
    
    # Process in batches to avoid overwhelming the site or getting blocked
    for i in range(0, len(question_numbers), batch_size):
        batch = question_numbers[i:i+batch_size]
        console.print(f"[cyan]Processing batch: questions {batch}[/]")
        
        # Process questions in this batch
        tasks = []
        for question_number in batch:
            task = get_question_via_search(
                certification,
                topic_number,
                question_number,
                provider,
                display_name,
                url_pattern
            )
            tasks.append(task)
        
        # Wait for all tasks in this batch
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for question_number, result in zip(batch, batch_results):
            if isinstance(result, Exception):
                console.print(f"[red]Error scraping question {question_number}: {str(result)}[/]")
            elif result:
                results.append(result)
        
        # Add a delay between batches
        if i + batch_size < len(question_numbers):
            delay = random.uniform(10, 20)
            console.print(f"[cyan]Waiting {delay:.1f} seconds before next batch...[/]")
            await asyncio.sleep(delay)
    
    # Save the combined results
    output_dir = Path(f"data/{certification}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if results:
        output_file = output_dir / f"{certification}_search_scraped_questions.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        
        console.print(f"[bold green]Successfully scraped and saved {len(results)} questions via search[/]")
    
    return results
