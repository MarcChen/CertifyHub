#!/usr/bin/env python3
"""
Browser utilities for ExamTopics scraper
"""

import asyncio
import random
import time
from typing import Tuple, List, Optional
from playwright.async_api import async_playwright, Page, BrowserContext, Response
from rich.console import Console
import requests
from requests.exceptions import RequestException
from bs4 import BeautifulSoup

console = Console()

# User agents to rotate for anti-detection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_0_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Safari/537.36 Edg/96.0.1054.29",
]

# Proxy pool for rotating IPs
FREE_PROXY_SOURCES = [
    "https://free-proxy-list.net/",
    "https://www.sslproxies.org/",
    "https://www.us-proxy.org/",
]


def get_proxies() -> List[str]:
    """
    Get free proxies from various sources
    
    Returns:
        List of proxy strings in format "ip:port"
    """
    proxy_list = []
    
    for source in FREE_PROXY_SOURCES:
        try:
            response = requests.get(source, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                table = soup.find('table', id='proxylisttable')
                
                if table:
                    # Process table rows to extract proxies
                    for row in table.find_all('tr')[1:]:
                        columns = row.find_all('td')
                        if len(columns) >= 2:
                            ip = columns[0].text.strip()
                            port = columns[1].text.strip()
                            
                            # Check if HTTPS is supported (optional)
                            https = columns[6].text.strip() if len(columns) > 6 else "no"
                            
                            # Add as proxy if it supports HTTPS
                            if https.lower() == "yes":
                                proxy = f"{ip}:{port}"
                                proxy_list.append(proxy)
        
        except (RequestException, Exception) as e:
            console.print(f"[yellow]Failed to fetch proxies from {source}: {str(e)}[/]")
            continue
    
    # Return unique proxies
    return list(set(proxy_list))


async def setup_browser_context(playwright, headless=True) -> Tuple[BrowserContext, Page]:
    """
    Set up a browser context with configurations to avoid detection.
    
    Args:
        playwright: The playwright instance
        headless: Whether to run the browser in headless mode
    
    Returns:
        Tuple of browser context and page
    """
    # Use a random user agent
    user_agent = random.choice(USER_AGENTS)
    console.print(f"[bold green]Using User-Agent:[/] {user_agent}")
    
    # Get proxies only occasionally to avoid overusing proxy sources
    proxy = None
    if random.random() < 0.3:  # 30% chance of using a proxy
        proxies = get_proxies()
        if proxies:
            proxy = random.choice(proxies)
            console.print(f"[bold green]Using proxy:[/] {proxy}")
    
    # Set up the browser with specific configurations to avoid detection
    browser_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-infobars",
        "--window-position=0,0",
        "--ignore-certificate-errors",
        "--ignore-certificate-errors-spki-list",
        "--disable-dev-shm-usage",
        "--disable-accelerated-2d-canvas",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--disable-popup-blocking",
    ]
    
    browser = await playwright.chromium.launch(
        headless=headless,
        args=browser_args
    )
    
    # Browser context options
    context_options = {
        "user_agent": user_agent,
        "viewport": {"width": 1280, "height": 1080},
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "permissions": ["geolocation"],
        "geolocation": {"latitude": random.uniform(38.0, 42.0), "longitude": random.uniform(-75.0, -71.0)},  # Random US East Coast location
        # Emulate different devices sometimes
        "device_scale_factor": random.choice([1, 1.25, 1.5, 2]),
        "has_touch": random.random() > 0.7,  # 30% chance of touch support
    }
    
    # Add proxy if available
    if proxy:
        ip, port = proxy.split(':')
        context_options["proxy"] = {
            "server": f"http://{ip}:{port}"
        }
    
    # Create a context with specific device settings
    context = await browser.new_context(**context_options)
    
    # Add additional headers
    await context.set_extra_http_headers({
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    })
    
    # Create a page from the context
    page = await context.new_page()
    
    # Emulate human-like behavior by setting page properties
    await page.evaluate("""() => {
        // Override webdriver property
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        
        // Add fake plugins
        Object.defineProperty(navigator, 'plugins', { 
            get: () => [
                {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
                {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''},
                {name: 'Native Client', filename: 'internal-nacl-plugin', description: ''}
            ]
        });
        
        // Override languages property
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en', 'es'],
        });
        
        // Add a fake notification permission
        const originalPermission = window.Notification?.permission;
        Object.defineProperty(window.Notification || {}, 'permission', {
            get: () => originalPermission || 'default'
        });
        
        // Add fake canvas fingerprint
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type) {
            if (type === 'image/png' && this.width === 300 && this.height === 150) {
                // This is likely a fingerprinting attempt
                const dataURL = originalToDataURL.apply(this, arguments);
                // Add some random noise to the canvas data
                const randomValue = Math.floor(Math.random() * 10);
                return dataURL.replace('data:image/png', `data:image/png;base64,${randomValue}`);
            }
            return originalToDataURL.apply(this, arguments);
        };
    }""")
    
    return context, page


async def check_and_solve_captcha(page: Page) -> bool:
    """
    Check if a captcha is present and attempt to solve it automatically.
    
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
        "cloudflare",
        "human verification",
    ]
    
    # Check page content for captcha indicators
    content = await page.content()
    content_lower = content.lower()
    
    captcha_detected = False
    
    for indicator in captcha_indicators:
        if indicator in content_lower:
            console.print(f"[yellow]Captcha detected: '{indicator}' found on page[/]")
            captcha_detected = True
            break
    
    # Check for specific captcha elements if no indicator found in text
    if not captcha_detected:
        captcha_selectors = [
            "iframe[src*='recaptcha']",
            "iframe[src*='captcha']",
            "div.g-recaptcha",
            "form#captcha",
            "div.cf-turnstile",
            "div[id*='captcha']",
        ]
        
        for selector in captcha_selectors:
            element = await page.query_selector(selector)
            if element:
                console.print(f"[yellow]Captcha element detected: '{selector}'[/]")
                captcha_detected = True
                break
    
    if captcha_detected:
        await handle_captcha_automatically(page)
        return True
    
    return False


async def handle_captcha_automatically(page: Page) -> bool:
    """
    Use various techniques to try to bypass captcha without manual intervention.
    
    Args:
        page: The Playwright page
        
    Returns:
        True if bypassed successfully, False otherwise
    """
    # Strategy 1: Clear cookies and retry with different user-agent
    await page.context.clear_cookies()
    
    # Strategy 2: Wait random time to simulate human behavior
    wait_time = random.uniform(3, 7)
    console.print(f"[cyan]Waiting {wait_time:.1f} seconds before attempting captcha bypass...[/]")
    await asyncio.sleep(wait_time)
    
    # Strategy 3: Try to find and click "I'm not a robot" checkbox
    try:
        checkbox = await page.query_selector('div.recaptcha-checkbox-border')
        if checkbox:
            console.print("[cyan]Found reCAPTCHA checkbox, attempting to click it...[/]")
            await checkbox.click()
            await asyncio.sleep(1)
    except Exception:
        pass
    
    # Strategy 4: Try refreshing the page
    await page.reload()
    await asyncio.sleep(2)
    
    # Strategy 5: Try to interact with page elements naturally
    await human_like_interaction(page)
    
    # Strategy 6: Try to navigate through potential cloudflare protection
    try:
        cloudflare_form = await page.query_selector('form#challenge-form')
        if cloudflare_form:
            console.print("[cyan]Found Cloudflare challenge form, attempting to solve...[/]")
            # Sometimes just waiting is enough for Cloudflare to validate
            await asyncio.sleep(5)
            
            # Look for any challenge button and click it
            challenge_button = await page.query_selector('input[type="submit"], button[type="submit"]')
            if challenge_button:
                await challenge_button.click()
                await asyncio.sleep(3)
    except Exception:
        pass
    
    # Check if our bypass was successful
    still_captcha = False
    for indicator in ["captcha", "robot", "verify", "cloudflare"]:
        content = await page.content()
        if indicator in content.lower():
            still_captcha = True
            break
    
    if still_captcha:
        console.print("[red]Automatic captcha bypass attempts failed[/]")
        return False
    else:
        console.print("[green]Successfully bypassed captcha or protection[/]")
        return True


async def human_like_interaction(page: Page):
    """
    Simulate human-like interaction with the page.
    
    Args:
        page: The Playwright page
    """
    # Move mouse around randomly
    for _ in range(random.randint(3, 7)):
        x = random.randint(100, 1180)
        y = random.randint(100, 980)
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.1, 0.5))
    
    # Scroll up and down
    await human_like_scroll(page)
    
    # Simulate user typing in search box
    search_selectors = ["input[type='search']", "input[type='text']", "input[name='q']"]
    for selector in search_selectors:
        search_box = await page.query_selector(selector)
        if search_box:
            await search_box.click()
            await asyncio.sleep(random.uniform(0.2, 0.5))
            await search_box.type("exam questions", delay=random.uniform(100, 200))
            await asyncio.sleep(random.uniform(0.5, 1.0))
            await page.keyboard.press("Escape")
            await asyncio.sleep(random.uniform(0.5, 1.0))
            break


async def human_like_scroll(page: Page):
    """
    Simulates human-like scrolling behavior on a page.
    
    Args:
        page: The Playwright page
    """
    # Get page height
    height = await page.evaluate("document.body.scrollHeight")
    
    # Get viewport height
    viewport_height = await page.evaluate("window.innerHeight")
    
    # Calculate number of scrolls needed (with some randomness)
    num_scrolls = int(height / viewport_height) + random.randint(0, 2)
    
    # Start position
    current_position = 0
    
    for _ in range(num_scrolls):
        # Calculate a random scroll amount
        scroll_amount = random.randint(300, viewport_height)
        current_position += scroll_amount
        
        # Scroll to the new position
        await page.evaluate(f"window.scrollTo(0, {current_position})")
        
        # Add a random delay between scrolls
        await asyncio.sleep(random.uniform(0.3, 1.2))
        
        # Sometimes move back a bit to simulate natural behavior
        if random.random() < 0.2:  # 20% chance
            back_amount = random.randint(50, 150)
            current_position -= back_amount
            await page.evaluate(f"window.scrollTo(0, {current_position})")
            await asyncio.sleep(random.uniform(0.2, 0.5))


async def rotate_browser_context(playwright, max_attempts=3) -> Tuple[Optional[BrowserContext], Optional[Page]]:
    """
    Creates a new browser context with rotation of user agents, proxies, etc.
    Useful to overcome IP blocks or other restrictions.
    
    Args:
        playwright: The playwright instance
        max_attempts: Maximum number of attempts to create a working context
        
    Returns:
        Tuple of browser context and page, or (None, None) if failed
    """
    for attempt in range(max_attempts):
        try:
            console.print(f"[cyan]Attempt {attempt + 1}/{max_attempts} to create a fresh browser context...[/]")
            
            # Create a new browser context with anti-detection measures
            context, page = await setup_browser_context(playwright, headless=False)
            
            # Test the context by accessing a simple website
            await page.goto("https://www.example.com", timeout=30000)
            
            # If we get here, the context is working
            return context, page
            
        except Exception as e:
            console.print(f"[yellow]Failed to create working browser context (attempt {attempt + 1}): {str(e)}[/]")
            
            # Close the context if it exists
            try:
                await context.close()
            except:
                pass
                
            # Wait before the next attempt
            await asyncio.sleep(random.uniform(2, 5))
    
    console.print("[red]Failed to create a working browser context after multiple attempts[/]")
    return None, None


async def extract_content_behind_paywall(page: Page):
    """
    Attempts to extract content that's hidden behind a paywall overlay
    
    Args:
        page: The Playwright page with paywall
    
    Returns:
        The extracted HTML content or None if failed
    """
    try:
        # Most paywall implementations still load the content but hide it with overlays
        # Try to extract the content by running JavaScript
        content = await page.evaluate("""() => {
            // Find and remove annoying overlays
            const overlays = document.querySelectorAll('.paywall, .modal, .popup, .overlay, .subscription-required');
            overlays.forEach(overlay => {
                if (overlay && overlay.parentNode) {
                    overlay.parentNode.removeChild(overlay);
                }
            });
            
            // Reset CSS properties that might be hiding content
            const resetStyles = (elements) => {
                elements.forEach(element => {
                    if (element) {
                        element.style.overflow = 'visible';
                        element.style.position = 'static';
                        element.style.display = 'block';
                        element.style.filter = 'none';
                        element.style.opacity = '1';
                        element.classList.remove('blur');
                        element.classList.remove('hidden');
                    }
                });
            };
            
            // Reset body and html styles
            resetStyles([document.body, document.documentElement]);
            
            // Reset styles for content containers
            const contentElements = document.querySelectorAll('main, article, .content, .question, .exam-question');
            resetStyles(contentElements);
            
            // Return the document HTML after our modifications
            return document.documentElement.outerHTML;
        }""")
        
        console.print("[green]Successfully extracted content from behind paywall overlay[/]")
        return content
    
    except Exception as e:
        console.print(f"[yellow]Failed to extract content from behind paywall: {str(e)}[/]")
        return None
