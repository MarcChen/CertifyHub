#!/usr/bin/env python3
"""
Main entry point for ExamTopics scraper
"""

import asyncio
import argparse
from pathlib import Path
from rich.console import Console

from .config import CERTIFICATION_CONFIGS, DEFAULT_CERT
from .examtopics_scraper import ExamTopicsScraper

console = Console()


async def run_scraper(args):
    """
    Main function to run the scraper
    
    Args:
        args: Command line arguments
    """
    try:
        # Create and initialize the scraper
        scraper = ExamTopicsScraper(args.certification)
        
        if args.mode == "views":
            # Always scrape views 1 and 2 which are free
            view_numbers = [1, 2]
            await scraper.scrape_free_views(view_numbers, recursive=False)
            
        elif args.mode == "search":
            # Start from question 21 by default (after the free views)
            start_question = args.start_question if args.start_question else 21
            
            # Use the max_questions parameter to limit the total
            max_questions = args.max_questions
            
            await scraper.scrape_remaining_questions(
                start_question=start_question,
                max_questions=max_questions,
                topic_number=args.topic,
                batch_size=args.batch_size
            )
            
        elif args.mode == "all":
            # First scrape the free views (1 and 2)
            view_numbers = [1, 2]
            view_data = await scraper.scrape_free_views(view_numbers, recursive=False)
            
            # Then scrape remaining questions (from 21 onwards)
            start_question = 21  # After the first 20 questions from views 1 and 2
            max_questions = args.max_questions
            
            await scraper.scrape_remaining_questions(
                start_question=start_question,
                max_questions=max_questions,
                topic_number=args.topic,
                batch_size=args.batch_size
            )
        
        # Print final statistics
        scraper.print_completion_stats()
            
    except Exception as e:
        console.print(f"[bold red]Error:[/] {str(e)}")
        import traceback
        console.print(traceback.format_exc())
        return 1
    
    console.print("[bold green]Scraping complete![/]")
    return 0


def main():
    """Command-line entry point"""
    parser = argparse.ArgumentParser(description='ExamTopics Scraper')
    
    # Basic arguments
    parser.add_argument('--certification', '-c', type=str, default=DEFAULT_CERT,
                        choices=list(CERTIFICATION_CONFIGS.keys()),
                        help='Certification to scrape')
    
    parser.add_argument('--mode', '-m', type=str, 
                        choices=['views', 'search', 'all'], default='all',
                        help=('Scraping mode: views (scrape free view pages 1-2 only), '
                              'search (scrape specific questions via search), or '
                              'all (both methods)'))
    
    # Search scraping options
    parser.add_argument('--topic', '-t', type=int, default=1,
                        help='Topic number to use for search scraping')
    
    parser.add_argument('--max-questions', '-n', type=int, default=30,
                        help='Maximum number of questions to scrape (default: 30)')
    
    parser.add_argument('--start-question', '-s', type=int, default=None,
                        help='Starting question number for search mode (default: 21)')
    
    parser.add_argument('--batch-size', '-b', type=int, default=3,
                        help='Number of questions to process in parallel during search scraping')
    
    args = parser.parse_args()
    
    # Run the scraper
    exit_code = asyncio.run(run_scraper(args))
    return exit_code


if __name__ == "__main__":
    exit(main())
