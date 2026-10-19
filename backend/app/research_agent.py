from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
import os
from typing import TypedDict, Annotated, List, Literal
from playwright.async_api import Page
from operator import add
from pydantic import BaseModel, Field
from Browser.webrover_browser import WebRoverBrowser
import asyncio
from playwright.async_api import async_playwright
from playwright.async_api import Page, Locator
import platform
from langchain_text_splitters import NLTKTextSplitter, SpacyTextSplitter
from newspaper import Article
import aiohttp
import asyncio
from io import BytesIO
from PyPDF2 import PdfReader
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import OpenAIEmbeddings
from langgraph.graph import START, END, StateGraph
from IPython.display import Image, display
import nltk



embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

load_dotenv()
def set_env_vars(var):
    value = os.getenv(var)
    if value is not None:
        os.environ[var] = value


vars = ["OPENAI_API_KEY", "LANGCHAIN_API_KEY", "LANGCHAIN_TRACING_V2", "LANGCHAIN_ENDPOINT", "LANGCHAIN_PROJECT", "TAVILY_API_KEY", "ANTHROPIC_API_KEY"]

for var in vars:
    set_env_vars(var)

llm_4o = ChatOpenAI(model="gpt-4o", temperature=0)
llm_mini = ChatOpenAI(model="gpt-4o-mini", temperature=0)
llm_o3_mini = ChatOpenAI(model="o3-mini", reasoning_effort="high")

llm_anthropic = ChatAnthropic(model="claude-3-5-sonnet-20240620", temperature=0)
llm_openai_o1 = ChatOpenAI(model="o1-preview", temperature=1)
llm = llm_4o


class Url(BaseModel):
    url: str | Literal["NO_CHANGE"] = Field(description="The url to navigate to")

class SelfReview(BaseModel):
    answer: Literal["Yes", "No"]
    reasoning: str
    
class DomElement(TypedDict):
    index : int
    text : str
    type : str
    xpath : str
    x: float
    y: float
    description : str


class Action(TypedDict):
    thought : str
    action_type : Literal["click", "type", "scroll_read", "close_page", "wait", "go_back", "go_to_search", "retry", "respond"]
    args : str 
    action_element : DomElement

    
class AgentState(TypedDict):
    input: str
    page : Page
    dom_elements : List[DomElement]

    action : Action
    actions_taken : Annotated[List[str], add]
    visited_urls : Annotated[List[str], add]
    conversation_history: Annotated[List[str], add]
    new_page: Literal[True, False]
    answer: str
    is_pdf: Literal[True, False]


    

async def setup_browser(go_to_page: str):
    print(f"Setting up browser for {go_to_page}")
    browser = WebRoverBrowser()
    browser, context = await browser.connect_to_chrome()

    page = await context.new_page()
    
    try:
        await page.goto(go_to_page, timeout=80000, wait_until="domcontentloaded")
    except Exception as e:
        print(f"Error loading page: {e}")
        # Fallback to Google if the original page fails to load/
        
        await page.goto("https://www.google.com", timeout=100000, wait_until="domcontentloaded")

    return browser, page



# Screen Annotations


# Load the JavaScript file
with open("marking_scripts/final_marking.js", "r", encoding="utf-8") as f:
    marking_script = f.read()

async def execute_script(page):

    await asyncio.sleep(3)
    
    # Run the JavaScript marking function
    dom_tree = await page.evaluate(f"""
        (function() {{
            {marking_script}
            return captureInteractiveElements();
        }})();
    """)

        
    return dom_tree

async def remove_highlights(page):

    await asyncio.sleep(1)
    # Ensure the function is executed properly
    await page.evaluate("""
        (function() {
            if (typeof unmarkElements === 'function') {
                unmarkElements();
            } else {
                console.error('unmarkElements() not found. Re-injecting...');
                (function() {
                    function unmarkElements() {
                        console.log("Removing highlights...");

                        // Remove highlight container
                        const highlightContainer = document.getElementById('web-agent-highlight-container');
                        if (highlightContainer) {
                            highlightContainer.remove();
                            console.log("Highlight container removed.");
                        }

                        // Remove all highlight overlays
                        document.querySelectorAll("div").forEach(el => {
                            const style = window.getComputedStyle(el);
                            if (
                                (el.id && el.id.includes("highlight")) || 
                                style.border.includes("2px solid") || 
                                style.backgroundColor.includes("22") || 
                                style.zIndex === "2147483647"
                            ) {
                                el.remove();
                            }
                        });

                        // Remove lingering elements
                        setTimeout(() => {
                            document.querySelectorAll("[id^='highlight-'], div[style*='border: 2px solid'], div[style*='z-index: 2147483647']")
                                .forEach(el => el.remove());
                        }, 100);
                    }

                    unmarkElements();
                })();
            }
        })();
    """)


# Click

async def click(state: AgentState):
    page = state["page"]
    element_type = state["action"]["action_element"]["type"]
    try:    
        xpath = state["action"]["action_element"]["xpath"]
    except Exception as e:
        bbox_x = state["action"]["action_element"]["x"]
        bbox_y = state["action"]["action_element"]["y"]

    # Scroll the element into view using its XPath
    try:
        await page.evaluate(
            """
            (xpath) => {
                const result = document.evaluate(
                    xpath, 
                    document, 
                    null, 
                    XPathResult.FIRST_ORDERED_NODE_TYPE, 
                    null
                );
                const element = result.singleNodeValue;
                if (element) {
                    element.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
                }
            }
            """,
            xpath
        )
    except Exception as e:
        return {
            "actions_taken": ["Failed to scroll element into view, retrying..."],
            "page": state["page"],
            "new_page": False
        }

    try:
        element = page.locator(f'xpath={xpath}')
        if element_type == "link":
            try:
                async with page.context.expect_page(timeout=10000) as new_page_info:
                    if platform.system() == "Darwin":
                        await element.click(modifiers=["Meta"], timeout=5000)
                    else:
                        await element.click(modifiers=["Control"], timeout=5000)
                    
                try:
                    new_page = await new_page_info.value
                    if new_page:
                        await new_page.bring_to_front()
                        await new_page.wait_for_load_state("domcontentloaded", timeout=10000)
                        state["page"] = new_page
                    else:
                        return {
                            "actions_taken": ["Link click didn't open new page, retrying..."],
                            "page": state["page"],
                            "new_page": False
                        }
                except TimeoutError:
                    return {
                        "actions_taken": ["Page load timed out, retrying..."],
                        "page": state["page"],
                        "new_page": False
                    }
            except TimeoutError:
                # Fallback to coordinate-based clicking if element click times out
                return {
                    "actions_taken": ["Element click timed out, retrying with coordinates..."],
                    "page": state["page"],
                    "new_page": False
                }
        else:
            await element.click(timeout=5000)

    except Exception as fallback:
        # Coordinate-based clicking fallback
        try:
            bbox_x = state["action"]["action_element"]["x"]
            bbox_y = state["action"]["action_element"]["y"]
            
            if element_type == "link":
                try:
                    async with page.context.expect_page(timeout=10000) as new_page_info:
                        if platform.system() == "Darwin":
                            await page.keyboard.down("Meta")
                            await page.mouse.click(bbox_x, bbox_y, click_count=3)
                            await page.keyboard.up("Meta")
                        else:
                            await page.keyboard.down("Control")
                            await page.mouse.click(bbox_x, bbox_y, click_count=3)
                            await page.keyboard.up("Control")
                        
                        try:
                            new_page = await new_page_info.value
                            if new_page:
                                await new_page.bring_to_front()
                                await new_page.wait_for_load_state("domcontentloaded", timeout=10000)
                                state["page"] = new_page
                            else:
                                return {
                                    "actions_taken": ["Coordinate click didn't open new page, retrying..."],
                                    "page": state["page"],
                                    "new_page": False
                                }
                        except TimeoutError:
                            return {
                                "actions_taken": ["Page load timed out after coordinate click, retrying..."],
                                "page": state["page"],
                                "new_page": False
                            }
                except TimeoutError:
                    return {
                        "actions_taken": ["Coordinate click timed out, retrying..."],
                        "page": state["page"],
                        "new_page": False
                    }
            else:
                await page.mouse.click(bbox_x, bbox_y)
        except Exception as e:
            await page.evaluate("""
                async () => {
                    const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
                    
                    // Scroll back to the top after scrolling down
                    window.scrollTo({ top: 0, left: 0, behavior: 'smooth' });
                    
                    // Wait until the scroll position reaches the top
                    while (window.scrollY > 0) {
                        await delay(100);
                    }
                }
                """)
            return {
                "actions_taken": ["All click attempts failed, retrying..."],
                "page": state["page"],
                "new_page": False
            }

    await asyncio.sleep(2)
    
    element_description = (
        f"{state['action']['action_element']['type']} element "
        f"{state['action']['action_element']['description']}"
    )
    
    if state["page"] == page:
        return {"actions_taken": [f"Clicked {element_description}"], "page": state["page"], "new_page": False}
    else:
        return {"actions_taken": [f"Clicked {element_description}"], "page": state["page"], "new_page": True}
    

# After Click Router

async def after_click_router(state: AgentState):
    if state["new_page"]:
        return "scroll_and_read"
    else:
        return "annotate_page"
    
# Type

async def type(state: AgentState):
    """Types text into an input field located by its XPath, fallback bounding box if XPath fails."""
    page = state["page"]
    text = state["action"]["args"]
    
    
        
    try:
        bbox_x, bbox_y = state["action"]["action_element"]["x"], state["action"]["action_element"]["y"]
        await page.mouse.click(bbox_x, bbox_y, click_count=3)
        await asyncio.sleep(1)
        select_all = "Meta+A" if platform.system() == "Darwin" else "Control+A"
        await page.keyboard.press(select_all)
        await asyncio.sleep(1)
        await page.keyboard.press("Backspace")
        await asyncio.sleep(1)
        await page.keyboard.type(text)
        await asyncio.sleep(4)

    except Exception as e:
        xpath = state["action"]["action_element"]["xpath"]
        await page.locator(f'xpath={xpath}').click()
        await asyncio.sleep(1)
        select_all = "document.execCommand('selectAll', false, null);"
        await page.locator(f'xpath={xpath}').evaluate(select_all)
        await asyncio.sleep(1)
        await page.locator(f'xpath={xpath}').type(text)
        await asyncio.sleep(4)
        

    element_description = f"{state['action']['action_element']['type']} element {state['action']['action_element']['description']}"
    await page.keyboard.press("Enter")
    await asyncio.sleep(2)
    
    return {"actions_taken": [f"Typed {text} into {element_description}"]}

# Scroll Page


async def scroll_page(state: AgentState):
    """Smoothly scrolls down until either the bottom of the page is reached or 10 scroll events have occurred, then scrolls back to the top."""
    page = state["page"]

    print(page.url)
    await page.evaluate("""
    async () => {
        const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
        let scrollCount = 0;
        
        // Scroll down until the bottom is reached or maximum 10 scrolls have been performed
        while (scrollCount < 10 && (window.innerHeight + window.scrollY) < document.body.scrollHeight) {
            window.scrollBy({ top: 500, left: 0, behavior: 'smooth' });
            scrollCount++;
            await delay(500);
        }
        
        // Scroll back to the top after scrolling down
        window.scrollTo({ top: 0, left: 0, behavior: 'smooth' });
        
        // Wait until the scroll position reaches the top
        while (window.scrollY > 0) {
            await delay(100);
        }
    }
    """)

    return {"actions_taken": [f"Scrolled down the page and collected information"]}


# Scroll PDF

async def scroll_pdf(state: AgentState):
    page = state["page"]
    # Click to ensure the PDF viewer is focused
    await page.mouse.click(300, 300)
    
    # Use smaller scroll increments for smoother scrolling.
    # For instance, scroll 100 pixels at a time, 50 times.
    for _ in range(50):
        await page.mouse.wheel(0, 300)
        await asyncio.sleep(0.1)

    for _ in range(10):
        await page.mouse.wheel(0, -1500)
        await asyncio.sleep(0.1)
    
    # Optionally, scroll back to the top.
    await page.evaluate("window.scrollTo({ top: 0, behavior: 'smooth' })")
    return {"actions_taken": ["Scrolled PDF viewer using smooth mouse wheel events"]}


# Close Page

async def close_page(state: AgentState):
    context = state["page"].context  # Get the browser context from the current page
    await state["page"].close()        # Close the current tab
    if context.pages:
        page = context.pages[-1]
    else:
        # Last tab was closed: open a fresh one on Google so the agent has a page to act on.
        page = await context.new_page()
        await page.goto("https://www.google.com", timeout=30000, wait_until="domcontentloaded")
    print(page.url)
    return {"actions_taken": [f"Closed the current tab and switched to the last opened tab"], "page": page}


# Close Opened Link

async def close_opened_link(state: AgentState):
    current_url = state["page"].url
    context = state["page"].context  # Get the browser context from the current page
    await state["page"].close()        # Close the current tab
    if context.pages:
        page = context.pages[-1]
    else:
        # Last tab was closed: open a fresh one on Google so the agent has a page to act on.
        page = await context.new_page()
        await page.goto("https://www.google.com", timeout=30000, wait_until="domcontentloaded")
    await page.evaluate("""
                async () => {
                    const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
                    
                    // Scroll back to the top after scrolling down
                    window.scrollTo({ top: 0, left: 0, behavior: 'smooth' });
                    
                    // Wait until the scroll position reaches the top
                    while (window.scrollY > 0) {
                        await delay(100);
                    }
                }
                """)
    print(page.url)
    return {"actions_taken": [f"Closed the opened link {current_url} and switched to {page.url}"], "page": page}


# Wait

async def wait(state: AgentState):
    """Waits for a specified amount of time."""
    seconds = state["action"]["args"]
    await asyncio.sleep(5)
    return {"actions_taken": [f"Waited for {seconds} seconds"]}



# Go back 

async def go_back(state: AgentState):
    """Goes back to the previous page by calling window.history.back() and waiting for a known element."""
    page = state["page"]
    # Trigger back navigation via JavaScript.
    previous_page = page.url
    await page.evaluate("window.history.back()")
    # Wait a bit for the navigation to complete.
    # Optionally, you can wait for a specific selector you expect on the previous page:
    # await page.wait_for_selector("css=selector-of-known-element", timeout=30000)
    await page.wait_for_timeout(5000)
    current_page = page.url
    return {"actions_taken": [f"Navigated back to {current_page} from {previous_page}"]}


# Go to Search

async def go_to_search(state: AgentState):
    """Goes to google.com"""
    page = state["page"]
    await page.goto("https://www.google.com", timeout=30000, wait_until="domcontentloaded")
    return {"actions_taken": [f"Navigated to Google"]}


# WebPage RAG

# Scrape Text



async def scrape_text(page):        
    # Evaluate JavaScript in the page context to extract text and images.

# URL of the news article
    url = page.url

    # Create an Article object
    article = Article(url)

    # Download the article's HTML content
    try:
        article.download()

        # Parse the downloaded content
        article.parse()

        data = article.text

        if data == "":
            return "No data found"

        return data
   
    except Exception as e:
        return "Forbidden"

    
# Scrape PDF

async def scrape_pdf(page):
    """
    Fetches the PDF file from the current page's URL and extracts its text.
    Returns:
        - Extracted text if successful.
        - "No data found" if no text is extracted.
        - "Forbidden" if the PDF could not be downloaded.
    """
    url = page.url
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                content = await response.read()
                pdf_data = BytesIO(content)
                try:
                    reader = PdfReader(pdf_data)
                    text = ""
                    for page_num in range(len(reader.pages)):
                        page_obj = reader.pages[page_num]
                        page_text = page_obj.extract_text()
                        if page_text:
                            text += page_text + "\n"
                    if text.strip() == "":
                        return "No data found"
                    return text
                except Exception as e:
                    print(f"Error parsing PDF: {e}")
                    return "Forbidden"
            else:
                return "Forbidden"


# Docs from Text

async def docs_from_text(data, url):
    text_splitter = SpacyTextSplitter(chunk_size=500, chunk_overlap=10)
    
    texts = text_splitter.split_text(data)

    docs = [Document(page_content=text, metadata={"source": url}) for text in texts]

    return docs

# Store Doc Embeddings

async def store_doc_embeddings(docs):

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    vector_store = Chroma(
        collection_name="webpage_rag",
        embedding_function=embeddings,
        persist_directory="./rag_store_webpage",  # Where to save data locally, remove if not necessary
    )

    vector_store.add_documents(docs)



async def web_page_rag(state: AgentState):
    try:
        page = state["page"]

        if state["is_pdf"]:
            result = await scrape_pdf(page)
        else:
            result = await scrape_text(page)

        if result == "Forbidden":
            return {"actions_taken": [f"Scraping the webpage {page.url} failed, should try another url"]}
        elif result == "No data found":
            return {"actions_taken": [f"No textual content found on the webpage {page.url}, try looking for url that has data"]}
        else:
            docs = await docs_from_text(result, page.url)
            print(len(docs))

            await store_doc_embeddings(docs)

            return {"actions_taken":[f"Scraped the url {page.url} and stored the information in a vector database for future reference"]}
    except Exception as e:
        print(f"Error in web_page_rag: {e}")
        return {"actions_taken": [f"Error processing page content: {str(e)}"]}


# Note Scroll Read

async def note_scroll_read(state: AgentState):
    page = state["page"]
   
    url = str(page.url)

    visited_urls = state.get("visited_urls", [])

    if url in visited_urls:
        return state
    else:
        return {"visited_urls": [url]}
    

# Url Decide Node

async def url_decide_node(state: AgentState):
    input = state["input"]

    system_message = """
    You are an expert at deciding the url to navigate to.
    You will be given a task provided by the user and conversation history and the current page url.
    You will need to decide the url to navigate to.

    If the user's task is continuing from the previous conversation and same topic, return as NO_CHANGE.
    
    If user has a completely new task, decide the url to navigate to.
     - If its is something related information collection, navigate to google.
     - If its is something related to a specific website, navigate to the website.
     - For eg -
        1. If the user asks for the latest news on Apple's stock price, navigate to google.
        2. If user is asking to send an email to a specific person, navigate to gmail.
        3. If user is asking to book a flight, navigate to google to be able to search for flight booking sites later.
        4. If user is asking to find a restaurant, navigate to google maps.
        5. If the user is asking to book a hotel, navigate to google and search for hotel booking sites.

    Use this trick to decide the url to navigate to.
        - If the task is super specific to a website an can be performed only on that website, navigate to that website.
        - If the task is generic and can be performed on multiple websites, navigate to google to be able to search for more options later.

    Note: While returning the url, return the url in the format of the url and no text associated with it.
    """

    human_prompt = """
    This is the task provided by the user: {input}
    This is the conversation history: {conversation_history}
    This is the current page url: {page_url}
    """

    input = state["input"]
    conversation_history = state.get("conversation_history", [])
    page = state["page"]

    human_message = human_prompt.format(input=input, conversation_history=conversation_history, page_url=page.url)

    messages = [
        SystemMessage(content=system_message),
        HumanMessage(content=human_message)
    ]

    structured_llm = llm_mini.with_structured_output(Url)
    response = structured_llm.invoke(messages)
    print(response)

    page = state["page"]
   

    if response.url == "NO_CHANGE":
        return {"page": page }
    else:
        await page.goto(response.url)
        return { "page": page }
    


async def annotate_page(state: AgentState):
    page = state["page"]
    dom_elements = await execute_script(page)

    await remove_highlights(page)

    if dom_elements and dom_elements[0]["type"] == "pdf":
        return {"dom_elements": dom_elements, "is_pdf": True}
    else:
        return {"dom_elements": dom_elements, "is_pdf": False}



# Llm Call Node

async def llm_call_node(state: AgentState):

    template = """ 
        You are WebRover, an autonomous AI agent designed to browse the web, interact with pages, and extract or aggregate information based on user queries—much like a human browsing the internet. You have access to the following tools:
            - Click Elements: Click on a specified element using its XPath. For links, open them in a new tab.
            - Type in Inputs: Type text into an input field identified by its XPath.
            - Scroll and Read (Scrape+RAG): Scroll down the page while scraping visible text and images to store in a vector database.
            - Close Page: Close the current tab and switch focus to the last opened tab.
            - Wait: Pause for a specified amount of time.
            - Go Back: Navigate back to the previous page.
            - Go to Search: Navigate to Google.

        Your inputs include:
            - The user's query (what the user wants to achieve).
            - A list of interactive DOM elements on the current page with properties: [xpath, type, text, description, x, y].
            - A record of actions taken so far.
            - A list of URLs already visited (do not revisit the same URL).

        Your task:
            - Decide the next best action (or a coherent sequence of actions) to move closer to fulfilling the user's request.
            - Evaluate the context by carefully reviewing the user's query, previous actions taken, visited URLs, and conversation history.
            - **Important:** When selecting a DOM element for an action, examine its "text" and "description" fields. For example, if the task is to input a departure date on Google Flights, only choose an input field if its description or visible text includes keywords like "departure", "depart", or "depart date". Do not select a generic input element that lacks specific contextual clues.
            - Avoid repeating the same search or action if it has already been performed without progress. If a search term or action was already attempted and yielded no new information, refine or change your approach.
            - Plan your steps: If multiple sequential actions are needed (e.g., scroll then click, or type a refined search query), output them in order until a page navigation or significant state change occurs.
            - Be natural and precise: Mimic human browsing behavior—click on visible links, type into search bars, scroll to reveal more content, and update your strategy if repeated results occur.

        Action guidelines:
            - Click Elements: Use for selecting links, buttons, or interactive items. If a link has already been followed (or if its URL is in the visited list), avoid re-clicking it.
            - Type in Inputs: Use for entering or refining search queries and form inputs. If the same query has been issued before, consider modifying or extending it.
            - Scroll and Read (Scrape+RAG): Use to gather content when no immediately actionable link is visible.
            - Close Page: Use when you need to exit a tab and return to a previous page.
            - Wait: Use to allow the page sufficient time to load or update after an action.
            - Go Back: Use when you need to return to a previous state or page.
            - Go to Search & WebPage Search: Use these to initiate or refine searches if no better actions are available.
            - Retry: Use only when you are unable to infer the next action from the current context.

        Output format:
            - Clearly output your action(s) in a structured format including:
                - Thought: Your reasoning behind the chosen action(s), considering previous attempts.
                - Action: The action to be taken.
                - Dom_element: (if applicable) the DOM element to interact with.
                - Reasoning: Detailed reasoning behind your action.
            - Do not output a repeated search term if it was already used and did not lead to progress; instead, suggest a refined or alternative approach.
            - Only output one coherent action or logical sequence of actions at a time, ensuring each step builds on previous actions logically and naturally.
        """



    prompt = ChatPromptTemplate(
    messages=[
        ("system", template),
        ("human", "Input: {input}"),
        ("human", "Actions Taken So far: {actions_taken}"),
        ("human", "Interactive Elements: {dom_elements}"),
        ("human", "Urls Already Visited: {visited_urls}"),
        
    ],
    input_variables=["input", "dom_elements", "actions_taken"],
    partial_variables={"actions_taken": [], "visited_urls": []},
    optional_variables=["actions_taken", "visited_urls"]
    )



    actions_taken = state.get("actions_taken", [])
    dom_elements = state["dom_elements"]
    input = state["input"]
    visited_urls = state.get("visited_urls", [])
    prompt_value = prompt.invoke({"actions_taken": actions_taken, "dom_elements": dom_elements, "input": input, "visited_urls": visited_urls})

    response = llm.with_structured_output(Action).invoke(prompt_value)

    action = response

    return {"action": action}



tools = {
    "click" : "click",
    "type" : "type",
    "scroll_read" : "scroll_and_read",
    "close_page" : "close_page",
    "wait" : "wait",
    "go_back" : "go_back",
    "go_to_search" : "go_to_search",
}

# Tool Router

def tool_router(state: AgentState):
    action = state["action"]
    action_type = action["action_type"]

    if action_type == 'retry':
        return "annotate_page"
    
    return tools[action_type]

# Scroll and Read
async def scroll_and_read(state: AgentState):

    page = state["page"]
    await page.wait_for_load_state("domcontentloaded")
    
    page = state["page"]
    result = await page.evaluate("""
        () => {
            const url = window.location.href.toLowerCase();
            const isPDF = url.endsWith('.pdf') ||
                document.querySelector("embed[type*='pdf']") ||
                document.querySelector("iframe[src*='.pdf']");
                
            if (isPDF) {
                return "pdf";
            } else {
                return "webpage";
            }
        }
    """)
    return { "is_pdf": result == "pdf" }



async def webpage_or_pdf(state: AgentState):
    is_pdf = state["is_pdf"]

    if is_pdf:
        return "scroll_pdf"
    else:
        return "scroll_page"



# Self Review

async def self_review(state: AgentState):
    vector_store = Chroma(
    collection_name="webpage_rag",
    embedding_function=embeddings,
    persist_directory="./rag_store_webpage",
)

    input_text = state["input"]
    relevant_docs = vector_store.similarity_search(input_text, k=60)

    print(f"Number of documents: {len(relevant_docs)}")

    system_message = """
    You are an expert at reviewing a set of relevant documents related to the user's query and deciding if the information is sufficient to answer the user's query.
    You will be given a user's query and a set of relevant documents.
    Answer only in the format of "Yes" or "No".

    Also state the reason for your answer.
    """

    human_prompt = """
    This is the user's query: {input}
    This is the set of documents: {relevant_docs}
    """

    human_message = human_prompt.format(input=input_text, relevant_docs=relevant_docs)

    messages = [
        SystemMessage(content=system_message),
        HumanMessage(content=human_message)
    ]

    structured_llm = llm.with_structured_output(SelfReview)
    response = structured_llm.invoke(messages)
    
    


    if len(relevant_docs) > 59  or response.answer == "Yes":
        if response.answer == "Yes":
            state["actions_taken"] = response.reasoning
        return {"actions_taken" : [f"I have enough information on {input_text}. I will now proceed to write the article on {input_text}"], "collect_more_info" : False}
    else:
        return {"actions_taken" : [f"I need more information on {input_text}. I should visit more websites to gather information on {input_text}"], "collect_more_info" : True}

# after self review
async def after_self_review_router(state: AgentState):
    collect_more_info = state["collect_more_info"]
    if collect_more_info:
        return "annotate_page"
    else:
        return "answer_node"
    
# Answer Node

async def answer_node(state: AgentState):

    vector_store = Chroma(
        collection_name="webpage_rag",
        embedding_function=embeddings,
        persist_directory="./rag_store_webpage",  # Where to save data locally, remove if not necessary
    )

    input = state["input"]

    total_docs = vector_store._collection.count() 
    print("Total docs: ", total_docs)
    relevant_docs = vector_store.similarity_search(input, k=total_docs)
    
    visited_urls = state.get("visited_urls", [])



    system_message = """
        Role: Expert Answer Assistant

        You will be given a user's query, the urls visited and a set of relevant documents to answer the query.
        You will need to answer the query based on the provided documents.
        To cite refences for the answer, use the source information mentioned in the metadata of the documents compared to the urls visited.

        You are an expert at answering the user's query based on the provided documents. Your response must adhere to the following guidelines:

        1. Provide a High-Quality and Insightful Answer
        Comprehensive Coverage: Address all aspects of the user's query in detail.
        Accuracy: Ensure all information is correct and well-reasoned.
        Insightfulness: Offer deep understanding and valuable insights on the topic.
        
        2. Enhance Clarity and Depth with Markdown Formatting
        Headings and Subheadings: Organize your answer with clear titles and sections.
        Bullet Points and Lists: Use bullet points or numbered lists to present key points or steps.
        Emphasis: Highlight important information using bold or italics where appropriate.
        Code Blocks: Use code formatting for any code snippets or technical terms.
        
        3. Include Supporting Evidence with Proper APA Citations
        In-text Citations: For every fact or claim from the documents, include an in-text citation in the format (website name, date accessed)
        
        Reference List:
        Add a "References" section at the end of your answer which lists all urls visited and used to answer the query.
        List all cited sources in numerical order, each on a new line.
        Ensure that the numbering in the reference list corresponds to the in-text citations.
        Crediting Sources: Provide sufficient information in the references so the user can identify each source.
        
        4. Ensure Consistent Formatting and Readability
        Consistency: Use Markdown formatting consistently throughout your answer.
        Readability: Make your response easy to read with a logical flow of information.
        Organization: Structure your answer so that it is well-organized and easy to follow.
        
        Your Task:

        1. Answer the Query
        Provide a comprehensive and detailed answer to the user's question.
        Ensure that all parts of the query are addressed thoroughly.
        
        2. Use Markdown Formatting
        Headings & Subheadings: Organize your response with appropriate headings.
        Bullet Points & Lists: Use these to outline key points or steps clearly.
        Emphasis: Apply bold, italics, or code formatting to highlight important information.
        Cite Your Sources

        3. In-text Citations: Include citations immediately after the information derived from a source, e.g., [1].
        
        4. References Section:
        Title this section as "References".
        List all sources in the order they were cited.
        Each reference should appear on a new line and include enough detail to identify the source.
        
        5. Ensure Readability
        Clarity: Write in clear and concise language.
        Depth: Provide thorough explanations and insights.
        Flow: Ensure that the answer transitions smoothly between sections.
        
        
        
        Example Format:

        Introduction
        Provide an introductory paragraph that outlines the main points of your answer.

        Main Heading 1
        Key point or explanation (website name 1, date accessed).
        
        Main Heading 2
        Step or item one (website name 1, date accessed).
        Step or item two (website name 2, date accessed).
        
        Conclusion
        Summarize the key takeaways from your answer.
        
        References

        1. (website name 1, date accessed)

        2. (website name 2, date accessed)

        By following these guidelines, your answer will be detailed, well-structured, and properly cited, ensuring a high-quality response that meets the user's needs.

    """

    human_prompt = """
    This is the user's query: {input}
    There are the relevant documents: {relevant_docs}
    The urls visited are, use them to cite the references in the answer: {visited_urls}
    """

    human_message = human_prompt.format(input=input, relevant_docs=relevant_docs, visited_urls=visited_urls)

    messages = [
        SystemMessage(content=system_message),
        HumanMessage(content=human_message)
    ]

    response = llm_o3_mini.invoke(messages)

    return {"answer": response.content, "conversation_history": [f"User : {input}"]+[f"WebRover : {response}"], "actions_taken" : [f"Research on {input} complete"]}


# Empty RAG Store

async def empty_rag_store(state : AgentState):

    vector_store = Chroma(
    collection_name="webpage_rag",
    embedding_function=embeddings,
    persist_directory="./rag_store_webpage",
    )

    try:
        client = vector_store._client  # Access the underlying Chroma client
        client.delete_collection("webpage_rag")
        return {"actions_taken" : ["Emptied Vector Store"]}

    except Exception as e:
        print(f"Error deleting collection: {e}")
        return {"actions_taken" : ["Error Emptying Vector Store"]}

    
# Graph


builder = StateGraph(AgentState)

builder.add_node("url_decide_node", url_decide_node)
builder.add_node("annotate_page", annotate_page)
builder.add_node("llm_call_node", llm_call_node)
builder.add_node("click", click)
builder.add_node("type", type)
builder.add_node("scroll_page", scroll_page)
builder.add_node("scroll_pdf", scroll_pdf)
builder.add_node("scroll_and_read", scroll_and_read)
builder.add_node("web_page_rag", web_page_rag)
builder.add_node("note_scroll_read", note_scroll_read)
builder.add_node("close_page", close_page)
builder.add_node("wait", wait)
builder.add_node("go_back", go_back)
builder.add_node("go_to_search", go_to_search)
builder.add_node("answer_node", answer_node)
builder.add_node("empty_rag_store", empty_rag_store)
builder.add_node("close_opened_link", close_opened_link)
builder.add_node("self_review", self_review)


builder.add_edge(START, "url_decide_node")
builder.add_edge("url_decide_node", "annotate_page")
builder.add_edge("annotate_page", "llm_call_node")
builder.add_conditional_edges("llm_call_node", tool_router, ["annotate_page", "click", "type", "scroll_and_read", "close_page", "wait", "go_back", "go_to_search"])
builder.add_edge("scroll_and_read", "web_page_rag")
builder.add_conditional_edges("scroll_and_read", webpage_or_pdf, ["scroll_page", "scroll_pdf"])
builder.add_edge("scroll_pdf", "note_scroll_read")
builder.add_edge("scroll_page", "note_scroll_read")
builder.add_edge("web_page_rag", "note_scroll_read")
builder.add_edge("note_scroll_read", "close_opened_link")
builder.add_edge("close_opened_link", "self_review")
builder.add_conditional_edges("self_review", after_self_review_router, ["annotate_page", "answer_node"])
builder.add_edge("answer_node", "empty_rag_store")
builder.add_edge("empty_rag_store", END)
builder.add_conditional_edges("click", after_click_router, ["annotate_page", "scroll_and_read"])
builder.add_edge("type", "annotate_page")
builder.add_edge("close_page", "annotate_page")
builder.add_edge("wait", "annotate_page")
builder.add_edge("go_back", "annotate_page")
builder.add_edge("go_to_search", "annotate_page")

research_agent = builder.compile()

