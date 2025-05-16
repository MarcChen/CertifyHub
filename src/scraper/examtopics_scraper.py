#!/usr/bin/env python3
"""
Main scraper class for ExamTopics
"""

import asyncio
import json
import re
import random
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, SpinnerColumn

from .config import CERTIFICATION_CONFIGS
from .view_scraper import scrape_exam_views
from .search_scraper import get_question_via_search, scrape_questions_from_list

console = Console()

class ExamTopicsScraper:
    """Main scraper class for ExamTopics"""
    
    def __init__(self, certification: str):
        """
        Initialize the scraper
        
        Args:
            certification: The certification key from CERTIFICATION_CONFIGS
        """
        if certification not in CERTIFICATION_CONFIGS:
            raise ValueError(f"Certification {certification} not found in config. "
                             f"Available certifications: {', '.join(CERTIFICATION_CONFIGS.keys())}")
        
        self.certification = certification
        self.config = CERTIFICATION_CONFIGS[certification]
        self.provider = self.config["provider"]
        self.display_name = self.config["display_name"]
        self.url_pattern = self.config["url_pattern"]
        self.target_url = self.config["target_url"]
        self.output_dir = Path(f"data/{certification}")
        
        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize the exam data
        self.exam_data = {
            "title": f"{self.display_name} Exam Questions",
            "description": f"Scraped from ExamTopics",
            "provider": self.provider,
            "certification": certification,
            "questions": []
        }
        
        # Try to load existing data
        self.output_file = self.output_dir / f"{certification}_questions.json"
        if self.output_file.exists():
            try:
                with open(self.output_file, "r", encoding="utf-8") as f:
                    self.exam_data = json.load(f)
                    console.print(f"[green]Loaded {len(self.exam_data['questions'])} existing questions from {self.output_file}[/]")
            except Exception as e:
                console.print(f"[yellow]Could not load existing data: {e}[/]")
    
    def save_data(self):
        """Save the current exam data to disk"""
        # Sort questions by question number before saving
        self.exam_data["questions"].sort(key=lambda q: q["question_number"])
        
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(self.exam_data, f, indent=2)
        
        console.print(f"[green]Saved {len(self.exam_data['questions'])} questions to {self.output_file}[/]")
    
    async def get_total_questions_count(self) -> int:
        """
        Try to determine the total number of questions from existing data
        or estimate based on currently scraped questions
        
        Returns:
            Estimated total questions count
        """
        # If we've already determined this value
        if "total_questions" in self.exam_data:
            return self.exam_data["total_questions"]
            
        # Check our existing questions
        if self.exam_data["questions"]:
            # Get highest question number we've seen
            max_question = max(q["question_number"] for q in self.exam_data["questions"])
            
            # Add some buffer room since we might not have all questions
            estimated_total = max(max_question, 300) # Most exams have at least 300 questions
            
            console.print(f"[yellow]Estimated total questions: {estimated_total}[/]")
            return estimated_total
            
        # Default to a reasonable number if we can't determine it
        return 300  # Most certification exams have at least 300 questions
    
    async def scrape_free_views(self, view_numbers: List[int] = None, recursive: bool = False) -> Dict[str, Any]:
        """
        Scrape questions from free view pages (typically views 1-2)
        
        Args:
            view_numbers: List of view numbers to scrape. Default [1, 2]
            recursive: Whether to automatically follow all views until no more questions found
            
        Returns:
            Dictionary containing the exam data
        """
        # Default to views 1 and 2 which are always free
        if view_numbers is None:
            view_numbers = [1, 2]
            
        console.print(f"[bold blue]Starting direct view scraping for {self.display_name}[/]")
        console.print(f"[bold blue]Scraping free view pages: {view_numbers}[/]")
        
        # Scrape the view pages
        view_data = await scrape_exam_views(
            self.certification,
            view_numbers,
            self.target_url,
            self.display_name,
            self.provider,
            recursive=recursive
        )
        
        # Extract the total questions count if available
        if view_data.get("total_questions", 0) > 0:
            self.exam_data["total_questions"] = view_data["total_questions"]
            console.print(f"[blue]Found total questions count: {self.exam_data['total_questions']}[/]")
        
        # Merge the scraped data with our existing data
        existing_question_numbers = {q["question_number"] for q in self.exam_data["questions"]}
        
        for question in view_data.get("questions", []):
            # Only add if we don't already have this question number
            if question["question_number"] not in existing_question_numbers:
                self.exam_data["questions"].append(question)
                existing_question_numbers.add(question["question_number"])
                console.print(f"[green]Added question {question['question_number']} from view {question.get('view_number', 'unknown')}[/]")
            else:
                # Update existing question if needed
                for i, existing_question in enumerate(self.exam_data["questions"]):
                    if existing_question["question_number"] == question["question_number"]:
                        # Only update if new data has more information
                        if (not existing_question.get("correct_answer") and question.get("correct_answer")) or \
                           (len(existing_question.get("choices", [])) < len(question.get("choices", []))):
                            self.exam_data["questions"][i] = question
                            console.print(f"[blue]Updated question {question['question_number']} with better data[/]")
                        break
        
        # Save the updated data
        self.save_data()
        
        return self.exam_data
    
    async def scrape_remaining_questions(
        self,
        start_question: int = 21,
        max_questions: int = 30,
        topic_number: int = 1,
        batch_size: int = 3
    ) -> Dict[str, Any]:
        """
        Scrape remaining questions via search method
        
        Args:
            start_question: Starting question number (default: 21, after the free view pages)
            max_questions: Maximum number of questions to scrape (default: 30)
            topic_number: The topic number to use
            batch_size: How many questions to process in a batch
            
        Returns:
            Dictionary containing the exam data
        """
        console.print(f"[bold blue]Starting search-based scraping for {self.display_name}[/]")
        
        # Determine existing question numbers
        existing_question_numbers = {q["question_number"] for q in self.exam_data["questions"]}
        
        # Get the total questions count or estimate
        total_expected = await self.get_total_questions_count()
        
        # Calculate the end question number based on max_questions
        # Either the last question number or start_question + max_questions - 1
        end_question = min(total_expected, start_question + max_questions - 1)
        
        # Create list of question numbers we need to scrape
        questions_to_scrape = [
            q for q in range(start_question, end_question + 1) 
            if q not in existing_question_numbers
        ]
        
        console.print(f"[blue]Starting from question {start_question}[/]")
        console.print(f"[blue]Scraping up to question {end_question}[/]")
        console.print(f"[blue]Need to scrape {len(questions_to_scrape)} questions[/]")
        
        # Track completed questions and failures
        completed = set()
        failed = set()
        
        # Process in batches
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console
        ) as progress:
            overall_task = progress.add_task(
                f"[cyan]Overall progress ({start_question}-{end_question})", 
                total=len(questions_to_scrape)
            )
            
            for i in range(0, len(questions_to_scrape), batch_size):
                batch = questions_to_scrape[i:i+batch_size]
                console.print(f"[cyan]Processing batch: questions {batch}[/]")
                
                # Scrape questions in this batch
                batch_task = progress.add_task(f"[cyan]Current batch", total=len(batch))
                
                # Process questions in this batch serially to avoid rate limiting
                for question_number in batch:
                    try:
                        # Skip already scraped questions
                        if question_number in existing_question_numbers:
                            console.print(f"[yellow]Skipping question {question_number} (already scraped)[/]")
                            progress.update(batch_task, advance=1)
                            progress.update(overall_task, advance=1)
                            continue
                        
                        # Use search scraper to get question data
                        question_data = await get_question_via_search(
                            self.certification,
                            topic_number,
                            question_number,
                            self.provider,
                            self.display_name,
                            self.url_pattern,
                            max_retries=2
                        )
                        
                        # If successful, add to our data
                        if question_data and question_data.get("question_text"):
                            self.exam_data["questions"].append(question_data)
                            existing_question_numbers.add(question_number)
                            completed.add(question_number)
                            console.print(f"[green]Successfully scraped question {question_number}[/]")
                            
                            # Save after each successful question as a checkpoint
                            self.save_data()
                        else:
                            console.print(f"[red]Failed to scrape question {question_number}[/]")
                            failed.add(question_number)
                    
                    except Exception as e:
                        console.print(f"[red]Error processing question {question_number}: {str(e)}[/]")
                        failed.add(question_number)
                    
                    # Update progress
                    progress.update(batch_task, advance=1)
                    progress.update(overall_task, advance=1)
                    
                    # Add a small delay between individual questions
                    await asyncio.sleep(random.uniform(2, 4))
                
                # Add a longer delay between batches
                if i + batch_size < len(questions_to_scrape):
                    delay = random.uniform(5, 10)
                    console.print(f"[cyan]Waiting {delay:.1f} seconds before next batch...[/]")
                    await asyncio.sleep(delay)
        
        # Save the final data
        self.save_data()
        
        # Print summary
        console.print(f"[bold green]Scraping complete![/]")
        console.print(f"[green]Successfully scraped: {len(completed)} questions[/]")
        console.print(f"[red]Failed to scrape: {len(failed)} questions[/]")
        
        return self.exam_data
    
    def get_completion_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the scraping completion
        
        Returns:
            Dictionary with statistics
        """
        total_questions = self.exam_data.get("total_questions", 0)
        if total_questions == 0 and self.exam_data["questions"]:
            # Estimate based on highest question number
            total_questions = max(q["question_number"] for q in self.exam_data["questions"])
        
        scraped_count = len(self.exam_data["questions"])
        
        # Count questions with correct answers
        with_answers = sum(1 for q in self.exam_data["questions"] if q.get("correct_answer"))
        
        stats = {
            "certification": self.certification,
            "display_name": self.display_name,
            "total_estimated_questions": total_questions,
            "scraped_questions": scraped_count,
            "with_answers": with_answers,
            "completion_percentage": (scraped_count / total_questions * 100) if total_questions > 0 else 0,
            "answers_percentage": (with_answers / scraped_count * 100) if scraped_count > 0 else 0
        }
        
        return stats
    
    def print_completion_stats(self):
        """Print completion statistics to the console"""
        stats = self.get_completion_stats()
        
        console.print(f"\n[bold cyan]===== {self.display_name} Scraping Statistics =====[/]")
        console.print(f"[blue]Estimated total questions:[/] {stats['total_estimated_questions']}")
        console.print(f"[green]Questions scraped:[/] {stats['scraped_questions']} ({stats['completion_percentage']:.1f}%)")
        console.print(f"[yellow]Questions with answers:[/] {stats['with_answers']} ({stats['answers_percentage']:.1f}%)")
        console.print(f"[bold cyan]==========================================[/]\n")
