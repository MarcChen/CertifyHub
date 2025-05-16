# ExamTopics Scraper

A robust scraper that extracts certification exam questions from ExamTopics without requiring manual captcha solving.

## Features

- **Fully Automated**: Handles captchas automatically using various bypass techniques
- **Two-Phase Scraping**:
  - Direct scraping of free view pages (views 1 and 2) which contain 20 questions total
  - Search-based scraping for remaining questions (21 onwards) 
- **Anti-Detection Measures**:
  - User agent rotation
  - Browser fingerprint manipulation
  - Human-like scrolling and interaction
  - Optional proxy rotation
- **Paywall Bypass**: Extracts content from behind paywalled sections
- **Robust Error Handling**: Automatic retries and recovery from failures
- **Incremental Saving**: Saves data as it's scraped to avoid data loss
- **Configurable Options**:
  - Multiple certification exam support
  - Maximum question limit setting
  - Recursive view page discovery
  - Controllable batch sizes

## Usage

### Basic Usage

```bash
python -m src.scraper.main --certification professional-machine-learning-engineer --recursive
```

### Command Line Options

- `--certification` / `-c`: Certification exam to scrape (default: professional-machine-learning-engineer)
- `--mode` / `-m`: Scraping mode: 'views', 'search', or 'all' (default: 'all')
- `--recursive` / `-r`: Recursively scrape all view pages (finds total questions automatically)
- `--total` / `-n`: Maximum number of questions to scrape
- `--batch-size` / `-b`: Number of questions to process in parallel during search phase
- `--topic` / `-t`: Topic number to use (default: 1)

### Examples

Scrape only the free view pages:
```bash
python -m src.scraper.main --mode views
```

Scrape specific questions via search:
```bash
python -m src.scraper.main --mode search --topic 1 --total 50
```

Scrape all questions with a limit:
```bash
python -m src.scraper.main --mode all --total 100
```

## How It Works

1. **Initialization**: Load configuration for the selected certification exam
2. **View Scraping Phase**:
   - Directly accesses view/1 and view/2 pages which are freely available
   - Extracts the total question count for the exam
   - Saves questions 1-20 (typically)
3. **Search Scraping Phase**:
   - For each remaining question (21 onwards, up to the limit):
   - Constructs search queries targeting specific question numbers
   - Uses search engines to find direct links to discussion pages
   - Extracts question data from behind any paywall obstacles
4. **Data Processing**:
   - Merges data from both phases
   - De-duplicates questions
   - Saves complete dataset to JSON file

## Advanced Features

- **Automatic Captcha Bypass**: Uses multiple techniques to automatically bypass captchas
- **Proxy Rotation**: Automatically rotates proxy servers to avoid IP-based blocking
- **Browser Anti-Detection**: Implements various measures to prevent bot detection
- **Progress Tracking**: Shows real-time progress and statistics during scraping