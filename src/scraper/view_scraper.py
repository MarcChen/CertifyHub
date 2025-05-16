#!/usr/bin/env python3
"""
View scraper for ExamTopics

This module handles scraping exam questions from free view pages on ExamTopics.
"""

import asyncio
import json
import re
import random
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page, BrowserContext
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .browser_utils import (
    setup_browser_context,
    check_and_solve_captcha,
    human_like_scroll,
    handle_captcha_automatically,
    rotate_browser_context,
    extract_content_behind_paywall
)

console = Console()


async def get_total_questions_count(page: Page) -> int:
    """
    Extract the total number of questions from the page.
    
    Args:
        page: The Playwright page
        
    Returns:
        Total number of questions or 0 if not found
    """
    try:
        # Try to find the element that contains the total questions count
        questions_info = await page.query_selector(".examQa__item:nth-child(4)")
        if questions_info:
            text = await questions_info.inner_text()
            # Extract the number from text like "Exam Questions: 358"
            match = re.search(r"Questions:\s*(\d+)", text)
            if match:
                return int(match.group(1))
    except Exception as e:
        console.print(f"[yellow]Error extracting question count: {e}[/]")
    
    # Alternative approach using page content
    try:
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        
        # Try to find text containing "questions" or "Exam Questions"
        for element in soup.find_all(['div', 'span', 'p']):
            text = element.get_text().strip()
            match = re.search(r"Questions:?\s*(\d+)", text, re.IGNORECASE)
            if match:
                return int(match.group(1))
    except Exception as e:
        console.print(f"[yellow]Failed to extract total questions using BeautifulSoup: {e}[/]")
        
    return 0


async def extract_question_data(question_elem) -> Dict[str, Any]:
    """
    Extract data from a question element.
    
    Args:
        question_elem: The question element from page.query_selector_all
        
    Returns:
        Dictionary with the extracted question data
    """
    question_data = {
        "question_id": "",
        "question_number": 0,
        "view_number": 0,
        "topic": "Unknown",
        "text": "",
        "choices": [],
        "correct_answer": "",
        "explanation": "",
        "community_votes": []
    }
    
    try:
        # Extract question header info
        question_header = await question_elem.query_selector("div.card-header")
        if question_header:
            question_full_number = await question_header.inner_text()
            # Parse question number from format like "Question #1"
            question_number_match = re.search(r"Question #(\d+)", question_full_number)
            if question_number_match:
                question_data["question_number"] = int(question_number_match.group(1))
        
        # Extract topic
        topic_span = await question_elem.query_selector(".question-title-topic")
        if topic_span:
            question_data["topic"] = await topic_span.inner_text()
        
        # Extract question body
        question_body = await question_elem.query_selector("div.question-body")
        if question_body:
            question_data["question_id"] = await question_body.get_attribute("data-id") or ""
            
            # Extract question text
            question_text_elem = await question_body.query_selector("p.card-text")
            if question_text_elem:
                question_data["text"] = (await question_text_elem.inner_html()).strip()
        
        # Extract choices
        choices_container = await question_elem.query_selector("div.question-choices-container")
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
                choice_text = choice_text.replace(f"{letter}.", "").strip()
                
                # Check if this choice is marked as correct
                is_correct = "correct-hidden" in (await choice_item.get_attribute("class") or "")
                
                question_data["choices"].append({
                    "letter": letter,
                    "text": choice_text,
                    "is_correct": is_correct
                })
                
                # If this choice is marked as correct, add it to correct_answer
                if is_correct:
                    question_data["correct_answer"] = letter
        
        # Get correct answer if not found from choices
        if not question_data["correct_answer"]:
            # Try to reveal solution if available
            reveal_btn = await question_elem.query_selector("a.reveal-solution")
            if reveal_btn:
                await reveal_btn.click()
                await asyncio.sleep(0.5)
            
            correct_answer_elem = await question_elem.query_selector("span.correct-answer")
            if correct_answer_elem:
                question_data["correct_answer"] = (await correct_answer_elem.inner_text()).strip()
        
        # Try to extract explanation
        explanation_elem = await question_elem.query_selector("div.question-explanation")
        if explanation_elem:
            question_data["explanation"] = (await explanation_elem.inner_text()).strip()
        
        # Extract community votes if available
        try:
            votes_script = await question_elem.query_selector(f"script#${question_data['question_id']}")
            if votes_script:
                votes_json = await votes_script.inner_text()
                question_data["community_votes"] = json.loads(votes_json)
        except Exception as e:
            console.print(f"[yellow]Error parsing votes data: {e}[/]")
        
    except Exception as e:
        console.print(f"[red]Error extracting question data: {str(e)}[/]")
    
    return question_data


async def scrape_exam_views(
    certification: str,
    view_numbers: List[int],
    target_url: str,
    display_name: str,
    provider: str,
    max_retries: int = 3,
    recursive: bool = True
) -> Dict[str, Any]:
    """
    Scrapes exam views (pages with 10 questions each) from ExamTopics.
    
    Args:
        certification: The certification key from CERTIFICATION_CONFIGS
        view_numbers: List of view numbers to scrape (1, 2, etc.)
        target_url: Base URL for the exam views
        display_name: Display name of the certification for output
        provider: The certification provider (e.g., "google")
        max_retries: Maximum number of retries for failed pages
        recursive: Whether to automatically scrape all views until no more questions are found
        
    Returns:
        Dictionary containing the extracted exam data from all views
    """
    output_dir = Path(f"data/{certification}")
    
    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    
    all_questions = []
    total_questions_count = 0
    exam_data = {
        "title": f"{display_name} Exam Questions",
        "description": f"Scraped from ExamTopics",
        "provider": provider,
        "certification": certification,
        "questions": []
    }
    
    # Track question numbers we've already scraped to avoid duplicates
    scraped_question_numbers = set()
    
    async with async_playwright() as p:
        # Try each view number
        view_number = 1  # Start with view 1
        consecutive_empty_views = 0
        max_consecutive_empty = 3  # Stop after finding 3 consecutive empty views
        
        while True:
            if not recursive and view_number > max(view_numbers):
                break
            
            # If recursive mode is off, only process views in the view_numbers list
            if not recursive and view_number not in view_numbers:
                view_number += 1
                continue
            
            # Construct the URL for this view
            view_url = f"{target_url}{view_number}/"
            console.print(f"[bold blue]Scraping {display_name} exam view #{view_number}:[/] {view_url}")
            
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                try:
                    # Setup browser with anti-detection measures
                    context, page = await rotate_browser_context(p)
                    if not context or not page:
                        console.print(f"[red]Failed to create browser context for view {view_number}. Skipping.[/]")
                        retry_count += 1
                        continue
                    
                    with console.status(f"[bold green]Loading exam view page {view_number}...") as status:
                        # Navigate to the page
                        await page.goto(view_url, wait_until="domcontentloaded", timeout=60000)
                        
                        # Check if we need to solve a captcha and attempt automatic solving
                        if await check_and_solve_captcha(page):
                            console.print(f"[yellow]Attempting to bypass captcha protection...[/]")
                            if not await handle_captcha_automatically(page):
                                # If automatic bypass failed, try refreshing with a new context
                                console.print(f"[yellow]Automatic captcha bypass failed. Retrying with fresh browser...[/]")
                                await context.close()
                                retry_count += 1
                                continue
                        
                        console.print(f"[green]✓[/] View {view_number} page loaded")
                        
                        # Extract total questions count if first view and we don't have it yet
                        if view_number == 1 and total_questions_count == 0:
                            total_questions_count = await get_total_questions_count(page)
                            if total_questions_count > 0:
                                console.print(f"[blue]Total questions for this exam: {total_questions_count}[/]")
                        
                        # Check for paywall or premium content notice
                        content = await page.content()
                        if "premium" in content.lower() or "subscribe" in content.lower() or "paywall" in content.lower():
                            console.print(f"[yellow]Detected paywall/premium content on view {view_number}[/]")
                            
                            # Try to extract content from behind the paywall
                            raw_content = await extract_content_behind_paywall(page)
                            if not raw_content:
                                console.print(f"[red]Could not extract content from behind paywall on view {view_number}[/]")
                            else:
                                content = raw_content
                        
                        # Find all question elements
                        with Progress(
                            SpinnerColumn(),
                            TextColumn("[bold blue]{task.description}"),
                            console=console
                        ) as progress:
                            task = progress.add_task(f"[bold blue]Extracting questions from view {view_number}...", total=None)
                            
                            # Query for all question cards
                            question_elements = await page.query_selector_all("div.exam-question-card")
                            
                            # If no questions found, check if we've hit the end
                            if not question_elements or len(question_elements) == 0:
                                console.print(f"[yellow]No questions found in view {view_number}[/]")
                                consecutive_empty_views += 1
                                success = True  # Mark as success to avoid retries for empty view
                                break
                            else:
                                consecutive_empty_views = 0  # Reset counter since we found questions
                            
                            progress.update(task, total=len(question_elements))
                            progress.start_task(task)
                            
                            view_questions_count = 0
                            
                            for i, question_elem in enumerate(question_elements):
                                try:
                                    # Extract all data for this question
                                    question_data = await extract_question_data(question_elem)
                                    question_data["view_number"] = view_number
                                    
                                    # Only add if this is a new question
                                    if question_data["question_number"] not in scraped_question_numbers:
                                        exam_data["questions"].append(question_data)
                                        scraped_question_numbers.add(question_data["question_number"])
                                        view_questions_count += 1
                                    
                                    progress.update(task, advance=1)
                                    
                                except Exception as e:
                                    console.print(f"[red]Error extracting question {i+1} in view {view_number}:[/] {str(e)}")
                            
                            console.print(f"[green]Extracted {view_questions_count} new questions from view {view_number}[/]")
                            
                        success = True
                
                except Exception as e:
                    console.print(f"[red]Error processing view {view_number} (attempt {retry_count + 1}): {str(e)}[/]")
                    retry_count += 1
                
                finally:
                    # Close context to free resources
                    if 'context' in locals():
                        await context.close()
            
            # If we've been successful or exhausted retries, move to the next view
            view_number += 1
            
            # Check if we should stop recursive scraping
            if recursive:
                # Stop if we found too many consecutive empty views
                if consecutive_empty_views >= max_consecutive_empty:
                    console.print(f"[yellow]Found {max_consecutive_empty} consecutive empty views. Stopping recursive scraping.[/]")
                    break
                
                # Stop if we've collected all questions based on the total count
                if total_questions_count > 0 and len(scraped_question_numbers) >= total_questions_count:
                    console.print(f"[green]Successfully scraped all {total_questions_count} questions. Stopping.[/]")
                    break
            
            # Add a delay between views to prevent blocking
            delay = random.uniform(5, 10)
            console.print(f"[cyan]Waiting {delay:.1f} seconds before processing next view...[/]")
            await asyncio.sleep(delay)
    
    # Calculate a completion percentage
    if total_questions_count > 0:
        completion_percentage = (len(exam_data["questions"]) / total_questions_count) * 100
        console.print(f"[green]Scraped {len(exam_data['questions'])} questions out of {total_questions_count} ({completion_percentage:.1f}%)[/]")
    else:
        console.print(f"[green]Scraped {len(exam_data['questions'])} questions in total[/]")
    
    # Save to JSON file
    output_file = output_dir / f"{certification}_questions_views.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(exam_data, f, indent=2)
    
    console.print(f"[bold green]Successfully scraped and saved exam view data to:[/] {output_file}")
    return exam_data
