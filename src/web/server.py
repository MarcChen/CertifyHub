#!/usr/bin/env python3
"""
CertifyHub Web Server

A simple web server to serve the scraped exam questions.
"""

import http.server
import socketserver
import json
from pathlib import Path
import os
from rich.console import Console
from typing import Dict, Any, List

console = Console()

# Default port for the web server
PORT = 8000

# Data directory where the scraped data is stored
DATA_DIR = Path("data")

# HTML template for the index page
INDEX_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CertifyHub - Exam Practice Portal</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            color: #333;
            max-width: 1000px;
            margin: 0 auto;
        }
        h1 {
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }
        h2 {
            color: #3498db;
            margin-top: 30px;
        }
        .exam-list {
            list-style-type: none;
            padding: 0;
        }
        .exam-item {
            background-color: #f8f9fa;
            margin-bottom: 15px;
            padding: 15px;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .exam-item h3 {
            margin-top: 0;
            color: #2c3e50;
        }
        .exam-item p {
            margin-bottom: 10px;
        }
        .exam-item a {
            display: inline-block;
            background-color: #3498db;
            color: white;
            padding: 8px 15px;
            text-decoration: none;
            border-radius: 4px;
            font-weight: bold;
        }
        .exam-item a:hover {
            background-color: #2980b9;
        }
    </style>
</head>
<body>
    <h1>CertifyHub - Exam Practice Portal</h1>
    <p>Welcome to CertifyHub, your resource for certification exam preparation.</p>
    
    <h2>Available Exams</h2>
    <ul class="exam-list" id="examList">
        <!-- Exam items will be populated by JavaScript -->
    </ul>

    <script>
        // Fetch the available exams
        fetch('/api/exams')
            .then(response => response.json())
            .then(exams => {
                const examList = document.getElementById('examList');
                exams.forEach(exam => {
                    const examItem = document.createElement('li');
                    examItem.className = 'exam-item';
                    
                    const title = document.createElement('h3');
                    title.textContent = exam.title;
                    
                    const description = document.createElement('p');
                    description.textContent = exam.description || 'No description available.';
                    
                    const questions = document.createElement('p');
                    questions.textContent = `Questions: ${exam.questionCount}`;
                    
                    const link = document.createElement('a');
                    link.href = `/exam/${exam.id}`;
                    link.textContent = 'Start Practice';
                    
                    examItem.appendChild(title);
                    examItem.appendChild(description);
                    examItem.appendChild(questions);
                    examItem.appendChild(link);
                    
                    examList.appendChild(examItem);
                });
            })
            .catch(err => {
                console.error('Error loading exams:', err);
                const examList = document.getElementById('examList');
                examList.innerHTML = '<p>Error loading exams. Please try again later.</p>';
            });
    </script>
</body>
</html>
"""

# HTML template for an exam page
EXAM_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - CertifyHub</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            color: #333;
            max-width: 1000px;
            margin: 0 auto;
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }}
        .question-card {{
            background-color: #f8f9fa;
            margin-bottom: 30px;
            padding: 20px;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        .question-header {{
            font-weight: bold;
            font-size: 1.2em;
            margin-bottom: 10px;
        }}
        .question-text {{
            margin-bottom: 20px;
        }}
        .choices {{
            list-style-type: none;
            padding: 0;
        }}
        .choice-item {{
            padding: 10px;
            margin-bottom: 5px;
            border: 1px solid #ddd;
            border-radius: 4px;
            cursor: pointer;
        }}
        .choice-item:hover {{
            background-color: #eee;
        }}
        .selected {{
            background-color: #d4edda;
            border-color: #c3e6cb;
        }}
        .discussion {{
            margin-top: 20px;
            padding: 15px;
            border-top: 1px solid #ddd;
            display: none;
        }}
        .show-discussion {{
            margin-top: 10px;
            background-color: #6c757d;
            color: white;
            border: none;
            padding: 8px 15px;
            border-radius: 4px;
            cursor: pointer;
        }}
        .show-discussion:hover {{
            background-color: #5a6268;
        }}
        .navigation {{
            display: flex;
            justify-content: space-between;
            margin: 20px 0;
        }}
        .navigation button {{
            background-color: #3498db;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
        }}
        .navigation button:hover {{
            background-color: #2980b9;
        }}
        .navigation button:disabled {{
            background-color: #cccccc;
            cursor: not-allowed;
        }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <div id="questionContainer"></div>
    
    <div class="navigation">
        <button id="prevBtn" disabled>Previous Question</button>
        <span id="questionCounter">Question 1 of {question_count}</span>
        <button id="nextBtn">Next Question</button>
    </div>
    
    <script>
        // The exam data
        const examData = {exam_data_json};
        let currentQuestionIndex = 0;
        
        function renderQuestion(index) {{
            const question = examData.questions[index];
            const container = document.getElementById('questionContainer');
            
            // Create question card
            const card = document.createElement('div');
            card.className = 'question-card';
            
            // Question header
            const header = document.createElement('div');
            header.className = 'question-header';
            header.textContent = question.number;
            
            // Question text
            const text = document.createElement('div');
            text.className = 'question-text';
            text.textContent = question.text;
            
            // Choices
            const choices = document.createElement('ul');
            choices.className = 'choices';
            
            question.choices.forEach((choice, i) => {{
                const choiceItem = document.createElement('li');
                choiceItem.className = 'choice-item';
                choiceItem.textContent = choice;
                choiceItem.onclick = function() {{
                    // Toggle selection
                    const selected = document.querySelector('.selected');
                    if (selected) {{
                        selected.classList.remove('selected');
                    }}
                    this.classList.add('selected');
                }};
                choices.appendChild(choiceItem);
            }});
            
            // Discussion
            const discussion = document.createElement('div');
            discussion.className = 'discussion';
            discussion.textContent = question.discussion || 'No discussion available.';
            
            // Show discussion button
            const showDiscussionBtn = document.createElement('button');
            showDiscussionBtn.className = 'show-discussion';
            showDiscussionBtn.textContent = 'Show Discussion';
            showDiscussionBtn.onclick = function() {{
                const disc = this.previousElementSibling;
                if (disc.style.display === 'block') {{
                    disc.style.display = 'none';
                    this.textContent = 'Show Discussion';
                }} else {{
                    disc.style.display = 'block';
                    this.textContent = 'Hide Discussion';
                }}
            }};
            
            // Assemble the card
            card.appendChild(header);
            card.appendChild(text);
            card.appendChild(choices);
            card.appendChild(discussion);
            card.appendChild(showDiscussionBtn);
            
            // Clear and add to container
            container.innerHTML = '';
            container.appendChild(card);
            
            // Update question counter
            document.getElementById('questionCounter').textContent = 
                `Question ${index + 1} of ${examData.questions.length}`;
                
            // Update navigation buttons
            document.getElementById('prevBtn').disabled = index === 0;
            document.getElementById('nextBtn').disabled = index === examData.questions.length - 1;
        }}
        
        // Navigation button handlers
        document.getElementById('prevBtn').onclick = function() {{
            if (currentQuestionIndex > 0) {{
                currentQuestionIndex--;
                renderQuestion(currentQuestionIndex);
            }}
        }};
        
        document.getElementById('nextBtn').onclick = function() {{
            if (currentQuestionIndex < examData.questions.length - 1) {{
                currentQuestionIndex++;
                renderQuestion(currentQuestionIndex);
            }}
        }};
        
        // Initial render
        renderQuestion(currentQuestionIndex);
    </script>
</body>
</html>
"""


def get_available_exams() -> List[Dict[str, Any]]:
    """Get a list of available exams from the data directory"""
    exams = []
    try:
        # Check all subdirectories in the DATA_DIR
        if DATA_DIR.exists():
            for exam_dir in [d for d in DATA_DIR.iterdir() if d.is_dir()]:
                # Look for JSON files in the directory
                json_files = list(exam_dir.glob("*.json"))
                
                for json_file in json_files:
                    try:
                        with open(json_file, "r", encoding="utf-8") as f:
                            exam_data = json.load(f)
                            
                        exam_id = exam_dir.name
                        title = exam_data.get("title", exam_id)
                        description = exam_data.get("description", "")
                        question_count = len(exam_data.get("questions", []))
                        
                        exams.append({
                            "id": exam_id,
                            "title": title,
                            "description": description,
                            "questionCount": question_count,
                            "filePath": str(json_file)
                        })
                    except Exception as e:
                        console.print(f"[red]Error loading exam from {json_file}:[/] {str(e)}")
    except Exception as e:
        console.print(f"[red]Error getting available exams:[/] {str(e)}")
    
    return exams


class CertifyHubHandler(http.server.SimpleHTTPRequestHandler):
    """Custom handler for the CertifyHub web server"""
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == "/":
            # Serve the index page
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(INDEX_TEMPLATE.encode("utf-8"))
            return
        
        elif self.path == "/api/exams":
            # Serve the list of available exams as JSON
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            exams = get_available_exams()
            self.wfile.write(json.dumps(exams).encode("utf-8"))
            return
        
        elif self.path.startswith("/exam/"):
            # Serve an exam page
            exam_id = self.path[6:]  # Remove "/exam/" prefix
            exams = get_available_exams()
            
            # Find the requested exam
            exam = next((e for e in exams if e["id"] == exam_id), None)
            if exam:
                try:
                    # Load the exam data
                    with open(exam["filePath"], "r", encoding="utf-8") as f:
                        exam_data = json.load(f)
                    
                    # Generate the exam page
                    exam_html = EXAM_TEMPLATE.format(
                        title=exam["title"],
                        question_count=exam["questionCount"],
                        exam_data_json=json.dumps(exam_data)
                    )
                    
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(exam_html.encode("utf-8"))
                    return
                except Exception as e:
                    console.print(f"[red]Error serving exam {exam_id}:[/] {str(e)}")
                    self.send_error(500, f"Error serving exam: {str(e)}")
                    return
            else:
                self.send_error(404, f"Exam {exam_id} not found")
                return
        
        # For all other requests, use the default handler
        return super().do_GET()


def run_server(port: int = PORT):
    """Run the web server on the specified port"""
    handler = CertifyHubHandler
    
    with socketserver.TCPServer(("", port), handler) as httpd:
        console.print(f"[bold green]Starting CertifyHub server on port {port}[/]")
        console.print(f"[bold]Open your browser and navigate to:[/] http://localhost:{port}/")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            console.print("[yellow]Server stopped.[/]")


if __name__ == "__main__":
    run_server()