from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
import os
from Browser.webrover_browser import WebRoverBrowser  
from typing import TypedDict, List, Annotated, Literal, Optional
from operator import add
from playwright.async_api import Page, Locator
from playwright.async_api import async_playwright
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
import asyncio
import platform

from IPython.display import Image, display
from langgraph.graph import StateGraph, START, END





class MasterPlan(TypedDict):
    master_plan: List[str]

class Url(BaseModel):
    url: str | Literal["NO_CHANGE"] = Field(description="The url to navigate to")

class DomElement(TypedDict):
    index : int
    text : str
    type : str
    xpath : str
    x: float
    y: float
    description : str
    inViewport: bool


class Action(TypedDict):
    thought: str
    action_type : Literal["click", "type"]
    args: str
    action_element: DomElement

class Actions(TypedDict):
    element_actions: Action

class DecideAction(TypedDict):
    thought: str
    step: Literal["decide_url", "get_all_elements", "get_all_input_elements", "get_all_button_elements", "get_all_link_elements", "go_back", "go_to_search", "respond", "wait" , "type_in_text_editor"]


class AgentState(TypedDict):
    input: str
    master_plan: MasterPlan
    page: Page
    dom_elements: List[DomElement]
    chat_history : Annotated[List[str], add]
    decide_action: DecideAction
    actions_taken: Annotated[List[str], add]
    actions: Actions
    response: str




load_dotenv()
def set_env_vars(var):
    value = os.getenv(var)
    if value is not None:
        os.environ[var] = value


vars = ["OPENAI_API_KEY", "LANGCHAIN_API_KEY", "LANGCHAIN_TRACING_V2", "LANGCHAIN_ENDPOINT", "LANGCHAIN_PROJECT", "TAVILY_API_KEY"]

for var in vars:
    set_env_vars(var)

llm_4o = ChatOpenAI(model="gpt-4o", temperature=0)
llm_mini = ChatOpenAI(model="gpt-4o-mini", temperature=0)
llm_o3_mini = ChatOpenAI(model="o3-mini", reasoning_effort="high")

llm_anthropic = ChatAnthropic(model="claude-3-5-sonnet-20240620", temperature=0)
llm_openai_o1 = ChatOpenAI(model="o1-preview", temperature=1)
llm = llm_4o

  

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


# Decide URL Node

async def decide_url(state: AgentState):
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
    conversation_history = state.get("chat_history", [])
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
        return {"page": page , "actions_taken": ["No change in the url, so I will continue with the same url"]}
    else:
        await page.goto(response.url)
        return { "page": page , "actions_taken": [f"Navigated to the {response.url}"]}
    

# Master Plan Node

async def master_plan_node(state: AgentState):

    system_template = """
    You are an expert a preparing a step by step plan to complete a task.
    You will be given a task provided by the user. The task might also be a question.
    You will need to prepare a plan to complete the task. In case its a question, you will need to prepare a plan to answer the question.

    You will be also provided the screenshot of the current web page.
    - If the current page is google home page or any other search engine, create a plan that basically searches the keyword and continues to the next step.
    - If the current page is not a some other web page, create a plan to scroll through the page and relevant collect information. 

    For eg if the task is "What is the lastest news on Apple's stock price?", you will need to prepare a plan to answer the question.
    You will need to prepare a plan to complete the task.

    For example, if the task is "What is the latest news on Apple's stock price?", your plan might look like this:
    1. Go to Google
    2. Type "Apple stock price news today" in the search bar and press enter
    3. Click on the link to the reliable financial news source (like Reuters, Bloomberg, or CNBC).
    4. Scan the article for current stock price and recent developments
    5. If you have enough information, prepare a concise summary of the latest news and price movement
    6. If you do not have enough information, go back to the previous page and try a different source and collect more data until you have enough information to answer the question.

    Your plan should be clear, sequential, and focused on achieving the user's goal efficiently. 

    The input might also include conversation history and the give task related to the conversation history. Plan the steps to complete the task based on the conversation history in that case

    --Notes--
    The browser is already open. First page will always be google, so plan accordingly with a search term.
    For any question, you will need to go to google and search for the question.
    """ 


    input = state["input"]
    conversation_history = state.get("conversation_history", [])


    prompt = ChatPromptTemplate(
        messages=[
            ("system", system_template),
            ("human", "User input: {input}"),
            ("human", "Conversation History: {conversation_history}"),
        ],
        input_variables = ["input"],
        partial_variables = {"conversation_history": []},
        optional_variables= ["conversation_history"]
    )
    structured_llm = llm_mini.with_structured_output(MasterPlan)

    formatted_prompt = prompt.invoke({"input": input, "conversation_history": conversation_history})

    response = structured_llm.invoke(formatted_prompt)
    

    return {"master_plan": [response]}


# Scrape Text Node

async def scrape_text(page):

    text = await page.evaluate("""() => {
        return document.body.innerText;
    }""")
    return text


# Annotate Elements Node


# Load the JavaScript file
with open("marking_scripts/marking.js", "r", encoding="utf-8") as f:
    marking_script_all = f.read()

async def execute_script_all(page):

    await asyncio.sleep(3)
    
    # Run the JavaScript marking function
    dom_tree = await page.evaluate(f"""
        (function() {{
            {marking_script_all}
            return captureInteractiveElements();
        }})();
    """)

        
    return dom_tree

async def remove_highlights_all(page):

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

async def get_all_elements(state: AgentState):
    page = state["page"]
    dom_elements = await execute_script_all(page)

    await remove_highlights_all(page)

    return {"dom_elements": dom_elements, "actions_taken": ["Gathered dom elements of all the interactive elements on the page, now I need to decide what to do next."]}


# Annotate links node

# Load the JavaScript file
with open("marking_scripts/marking_links.js", "r", encoding="utf-8") as f:
    marking_scrip_links = f.read()

async def execute_script_links(page):

    await asyncio.sleep(3)
    
    # Run the JavaScript marking function
    dom_tree = await page.evaluate(f"""
        (function() {{
            {marking_scrip_links}
            return captureInteractiveElements();
        }})();
    """)

        
    return dom_tree

async def remove_highlights_links(page):

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

async def get_all_link_elements(state: AgentState):
    page = state["page"]
    dom_elements = await execute_script_links(page)


    await remove_highlights_links(page)

    return {"dom_elements": dom_elements, "actions_taken": ["Gathered dom elements of all the interactive link elements on the page"]}


# Annotate Input Elements Node


# Load the JavaScript file
with open("marking_scripts/marking_input.js", "r", encoding="utf-8") as f:
    marking_script_input = f.read()

async def execute_script_input(page):

    await asyncio.sleep(3)
    
    # Run the JavaScript marking function
    dom_tree = await page.evaluate(f"""
        (function() {{
            {marking_script_input}
            return captureInteractiveElements();
        }})();
    """)

        
    return dom_tree

async def remove_highlights_input(page):

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

async def get_all_input_elements(state: AgentState):
    page = state["page"]
    dom_elements = await execute_script_input(page)

    await remove_highlights_input(page)

    return {"dom_elements": dom_elements, "actions_taken": ["Gathered dom elements of all the interactive input elements on the page"]}



# Annotate Button Elements Node

# Load the JavaScript file
with open("marking_scripts/marking_buttons_2.js", "r", encoding="utf-8") as f:
    marking_script_buttons = f.read()

async def execute_script_buttons(page):

    await asyncio.sleep(3)
    
    # Run the JavaScript marking function
    dom_tree = await page.evaluate(f"""
        (function() {{
            {marking_script_buttons}
            return captureInteractiveElements();
        }})();
    """)

        
    return dom_tree

async def remove_highlights_buttons(page):

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

async def get_all_button_elements(state: AgentState):
    page = state["page"]
    dom_elements = await execute_script_buttons(page)


    await remove_highlights_buttons(page)

    return {"dom_elements": dom_elements, "actions_taken": ["Gathered dom elements of all the interactive button elements on the page"]}



# Decide Action Node

async def decide_immediate_action(state: AgentState):

    text_on_page = await scrape_text(state["page"])

    system_message = """ 

        WebRover is an autonomous AI agent designed to browse the web, interact with pages, and complete tasks on behalf of user based on user input.
        
        You are a crucial part of WebRover AI agent, whose job is to assess the steps you need to take on higher level inorder to perform actions that will interact with web elements.

        To assess you with the answering what is the next best action, you will be given:
        1. User Input - The task that user wants to perform
        2. Actions Taken so far
        3. The current page url
        4. Text displayed on the current page
        

        Your answer should be strictly the following:
        1. Decide Url: Decide the url you need to visit in order to execute the task give by user
            - This will most probably  be the first thing you will do
        2. Get all elements: Get all interactable elements
            - This will most probably be the step you take if no action have been take so far on the web elements (Actions Taken so far is empty).
            - This will also be the step you take if you believe you have executed all the actions, just to check if there is still any action left to be taken. For example, if you have already clicked on a button, you will get all the elements again to check if there is any other button to be clicked. Always do this before you respond.
        3. Get all input elements: This will be the step you take if you decide you need to type in some text input
        4. Get all button elements: This will be the step you take if you decied to click on a button
        5. Get all link elements: This will be the action you take if you decide you need to open a link
        6. Go Back: If you decide you need to go back to the previous page, you should respond with "Go Back"
        7. Go To Search: If you decide you need to go to a search engine, you should respond with "Go To Search"
            - Avoid to call Go To Search if you are already on google.com as indicated by the current page url or if you have already navigated to google.com in the previous step.
        8. Wait: If you decide you need to wait for a page to load, you should respond with "Wait"
        9. Type in a text editor: If you decide you need to type in a text editor such as a google doc or some similar text editor based on the user input, you should respond with "Type in a text editor"
            - If you end up at a point where you need to type in a text editor after navigating to the respective text editor url, skip the other steps and directly respond with "Type in a text editor" since, this step has the ability to infer dom element for text editor
        10. Respond : If you believe you have executed all the actions to task completion and based ont the text on the page you believe you have an indication of the task completion or you have enough information to respond to the user, you should respond with "Respond"

        For reference - The elements that you fetch or url that you decide to visit will later be used to further infer the action to interact with web elements at a granualar level in other step. Such as clicking a button, clinking on a link or typing in a input element.


        Provide your answer in this format:
        Thought: Your reasoning behind the step you decided to take.
        Step: The exact step you decided

        Provide your answer : {{}}
        
    """
    human_message = """
    User Input : {input}
    Actions taken so far : {actions_taken}
    Current Page: {page}
    Text on the current page: {text_on_page}
    
    """

    input = state["input"]
    actions_taken = state.get("actions_taken", "")
    page = state["page"]


    messages = [SystemMessage(content=system_message), HumanMessage(content=human_message.format(input=input, actions_taken= actions_taken, page=page, text_on_page=text_on_page))]


    response = llm.with_structured_output(DecideAction).invoke(messages)

    return {"decide_action": response, "chat_history": state.get("chat_history", [])}


# Decide Immediate Action Router

async def decide_immediate_action_router(state: AgentState):
    
    decided_action = state["decide_action"]["step"]

    return decided_action



# Interact with Input Elements Node


async def interact_with_input_elements(state: AgentState):
    system_message = """ 
    WebRover is an autonomous AI agent designed to browse the web, interact with pages, and complete tasks on behalf of user based on user input.

    You are a crucial part of WebRover AI agent, whose job is to assess all the input elements on the current page and decide which one to interact with.

    To help you with the task, you will be given:
    1. All the input elements on the current page
    2. The user input
    3. The actions taken so far
    4. The current page you are on

    Your job is to create a list of input elements that you think are most likely to help you complete the task.

    Provide your answer for each input element in the list in this format:
    Thought: Your reasoning behind the input elements you decided to interact with.
    Input Element: The input element you decided to interact with.

    Provide your answer : {{}}

    """
    human_message = """
    User Input : {input}
    Actions taken so far : {actions_taken}
    Current Page: {page}
    All input elements on the current page: {input_elements}
    """

    input = state["input"]
    actions_taken = state.get("actions_taken", "")
    page = state["page"]
    input_elements = state["dom_elements"]

    messages = [SystemMessage(content=system_message), HumanMessage(content=human_message.format(input=input, actions_taken= actions_taken, page=page, input_elements=input_elements))]

    response = llm.with_structured_output(Actions).invoke(messages)

    return {"actions": response}

# Interact with Button Elements Node
async def interact_with_button_elements(state: AgentState):
    system_message = """ 
        WebRover is an autonomous AI agent designed to browse the web, interact with pages, and complete tasks on behalf of user based on user input.

        You are a crucial part of WebRover AI agent, whose job is to assess all the button elements on the current page and decide which one to interact with.

        To help you with the task, you will be given:
        1. All the button elements on the current page
        2. The user input
        3. The actions taken so far
        4. The current page you are on

        Your job is to identify the button elements that you think is most likely to help you complete the task. 


        Provide your answer for each button element in the list in this format:
        Thought: Your reasoning behind the button element you decided to interact with.
        Button Element: The button element you decided to interact with.


        Provide your answer : {{}}
        
        """
    
    human_message = """
    User Input : {input}
    Actions taken so far : {actions_taken}
    Current Page: {page}
    All button elements on the current page: {button_elements}
    """
    
    input = state["input"]
    actions_taken = state.get("actions_taken", "")
    page = state["page"]
    button_elements = state["dom_elements"]

    messages = [SystemMessage(content=system_message), HumanMessage(content=human_message.format(input=input, actions_taken= actions_taken, page=page, button_elements=button_elements))]

    response = llm.with_structured_output(Actions).invoke(messages)
    
    return {"actions": response}


# Interact with Link Elements Node

async def interact_with_link_elements(state: AgentState):
    system_message =""" 
        WebRover is an autonomous AI agent designed to browse the web, interact with pages, and complete tasks on behalf of user based on user input.

        You are a crucial part of WebRover AI agent, whose job is to assess all the link elements on the current page and decide which one to interact with.

        To help you with the task, you will be given:
        1. All the link elements on the current page
        2. The user input
        3. The actions taken so far
        4. The current page you are on

        Your job is to identify the link elements that you think is most likely to help you complete the task. 

        Provide your answer for each link element in the list in this format:   
        Thought: Your reasoning behind the link element you decided to interact with.
        Link Element: The link element you decided to interact with.

        Provide your answer : {{}}

    """

    human_message = """
    User Input : {input}
    Actions taken so far : {actions_taken}
    Current Page: {page}
    All link elements on the current page: {link_elements}
    """
    
    input = state["input"]
    actions_taken = state.get("actions_taken", "")
    page = state["page"]
    link_elements = state["dom_elements"]

    messages = [SystemMessage(content=system_message), HumanMessage(content=human_message.format(input=input, actions_taken=actions_taken, page=page, link_elements=link_elements))]
    
    response = llm.with_structured_output(Actions).invoke(messages)
    
    return {"actions": response}
    
    
# Type / Type in Text Editor Node

async def type(state: AgentState):
    """Types text into input fields."""
    page = state["page"]
    input_action = state["actions"]["element_actions"]
    old_page = page.url
    input_actions_taken = []

    inViewport = input_action["action_element"]["inViewport"]
    if inViewport == False:
        # First attempt: Smooth scroll into view
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
                        return true;
                    }
                    return false;
                }
                """,
                xpath
            )
            await asyncio.sleep(1)  # Allow smooth scroll to complete
        except Exception:
            # If smooth scroll fails, try instant scroll
            try:
                await page.evaluate(
                    """
                    (x, y) => {
                        window.scrollTo({
                            top: y - (window.innerHeight / 2),
                            behavior: 'instant'
                        });
                    }
                    """,
                    bbox_x, bbox_y
                )
                await asyncio.sleep(0.5)
            except Exception:
                return {"actions_taken": [f"Failed to scroll to element: {str(e)}"]}


    text = input_action["args"]
    print("Text to type: ", text)

    
    try:
        print("Using XPath")
        xpath = input_action["action_element"]["xpath"]
        element = page.locator(f'xpath={xpath}')
        print("Element: ", element)
        await asyncio.sleep(2)
        await element.click()
        print("Clicked")
        await asyncio.sleep(2)
        if platform.system() == "Darwin":
            await element.press("Meta+A")
        else:
            await element.press("Control+A")
        print("Selected")
        await element.press("Backspace")
        print("Backspace")
        await asyncio.sleep(2)
        await element.type(input_action["args"])
        print("Typed")
        await asyncio.sleep(2)
        await element.press("Enter")
        print("Enter")
        await asyncio.sleep(2)
        
        

    except Exception as e:
        try:
            # Fallback to coordinates
            print("Using Bounding Box")
            bbox_x = input_action["action_element"]["x"]
            bbox_y = input_action["action_element"]["y"]
            print("Bounding Box: ", bbox_x, bbox_y)
            
            await page.mouse.click(bbox_x, bbox_y)
            await asyncio.sleep(2)
            
            select_all = "Meta+A" if platform.system() == "Darwin" else "Control+A"
            await page.keyboard.press(select_all)
            await asyncio.sleep(2)
            await page.keyboard.press("Backspace")

                
            await asyncio.sleep(2)

            await page.mouse.click(bbox_x, bbox_y)
            
         
            await asyncio.sleep(2)
            await page.keyboard.type(input_action["args"])
            print("Typed")
            await asyncio.sleep(2)
            await page.keyboard.press("Enter")
            print("Enter")
            await asyncio.sleep(2)
            
            
        except Exception as e:
            input_actions_taken.append(f"Failed to type {text}")
            
        
    
    element_description = (
        f"{'input' if 'input' in input_action['action_element']['type'] else 'text area'} "
        f"element {input_action['action_element']['description']}"
    )

    await asyncio.sleep(5)

    action_type = input_action["action_type"] if input_action else None

    print("Action Type: ", action_type)

    
    if action_type == "type_in_text_editor":
        return {"actions_taken": ["I have successfully typed the entire report into the text editor"]}
    else:
        if old_page == page.url:
            print("Old Page: ", old_page)
            print("Actions Taken: ", [f"Typed {text} into {element_description}"])
            return {"actions_taken":[f"Typed {text} into {element_description}"], "new_page": False}
        else:
            print("Old Page: ", old_page)
            print("Actions Taken: ", [f"Typed {text} into {element_description}"])
            return {"actions_taken": [f"Typed {text} into {element_description}"], "new_page": True}
        



# Click


async def click(state: AgentState):
    """Handles clicking elements with improved error handling and retry logic."""
    
    click_actions_taken = []
    page = state["page"]
    old_page = page.url
    click_action = state["actions"]["element_actions"]

    element_type = click_action["action_element"]["type"]
      
    xpath = click_action["action_element"]["xpath"]
    bbox_x = click_action["action_element"]["x"]
    bbox_y = click_action["action_element"]["y"]
    inViewport = click_action["action_element"]["inViewport"]

    if inViewport == False:
        # First attempt: Smooth scroll into view
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
                        return true;
                    }
                    return false;
                }
                """,
                xpath
            )
            await asyncio.sleep(1)  # Allow smooth scroll to complete
        except Exception:
            # If smooth scroll fails, try instant scroll
            try:
                await page.evaluate(
                    """
                    (x, y) => {
                        window.scrollTo({
                            top: y - (window.innerHeight / 2),
                            behavior: 'instant'
                        });
                    }
                    """,
                    bbox_x, bbox_y
                )
                await asyncio.sleep(0.5)
            except Exception as e:
                return {"actions_taken": [f"Failed to scroll to element: {str(e)}"]}

    
    success = False
    attempts = 0
    max_attempts = 3

    while not success and attempts < max_attempts:
        attempts += 1
        try:
            if "link" in element_type:
                # Handle links with existing logic
                async with page.context.expect_page(timeout=10000) as new_page_info:
                    if platform.system() == "Darwin":
                        await page.locator(f'xpath={xpath}').click(
                            modifiers=["Meta"],
                            timeout=5000,
                            force=attempts == max_attempts  # Force click on last attempt
                        )
                    else:
                        await page.locator(f'xpath={xpath}').click(
                            modifiers=["Control"],
                            timeout=5000,
                            force=attempts == max_attempts
                        )
                    
                    new_page = await new_page_info.value
                    await asyncio.sleep(3)
                    await new_page.bring_to_front()
                    state["page"] = new_page
                    success = True
            else:
                # Enhanced button/element clicking
                try:
                    # Try precise click first
                    await page.locator(f'xpath={xpath}').click(
                        timeout=5000,
                        delay=100,  # Add slight delay for stability
                        force=attempts == max_attempts
                    )
                    success = True
                except Exception as e:
                    # If precise click fails, try coordinate click
                    if attempts == max_attempts - 1:
                        # On penultimate attempt, try clicking with JavaScript
                        await page.evaluate(
                            """
                            (xpath) => {
                                const element = document.evaluate(
                                    xpath,
                                    document,
                                    null,
                                    XPathResult.FIRST_ORDERED_NODE_TYPE,
                                    null
                                ).singleNodeValue;
                                if (element) {
                                    element.click();
                                    return true;
                                }
                                return false;
                            }
                            """,
                            xpath
                        )
                        await asyncio.sleep(1)
                    else:
                        # Try coordinate-based click
                        await page.mouse.click(
                            bbox_x,
                            bbox_y,
                            delay=100,
                            force=attempts == max_attempts
                        )
                    
                    # Wait briefly to check if click had an effect
                    await asyncio.sleep(1)
                    
                    # Check if page changed or any visible effect occurred
                    if page.url != old_page:
                        success = True
                    else:
                        # Additional check for button effect (e.g., style changes)
                        changed = await page.evaluate(
                            """
                            (xpath) => {
                                const element = document.evaluate(
                                    xpath,
                                    document,
                                    null,
                                    XPathResult.FIRST_ORDERED_NODE_TYPE,
                                    null
                                ).singleNodeValue;
                                return element && (
                                    element.matches(':active') ||
                                    element.matches(':focus') ||
                                    element.getAttribute('aria-expanded') === 'true'
                                );
                            }
                            """,
                            xpath
                        )
                        if changed:
                            success = True

        except Exception as e:
            if attempts == max_attempts:
                click_actions_taken.append(f"Failed to click {element_type} after {max_attempts} attempts")
                continue
            await asyncio.sleep(1)  # Brief pause before retry

        element_description = (
            f"{click_action['action_element']['text']} {click_action['action_element']['type']}"
        )
        if success:
            click_actions_taken.append(f"Successfully clicked {element_description}")
        
        # Check if we need to break the loop (page changed)
        if page.url != old_page:
            break

    # Return appropriate status
    if old_page == state["page"].url:
        return {"actions_taken": click_actions_taken, "new_page": False}
    else:
        return {"actions_taken": click_actions_taken, "new_page": True}
    


# Wait

async def wait(state: AgentState):
    await asyncio.sleep(10)
    return {"actions_taken": ["I have waited for 10 seconds"]}


# Go Back

async def go_back(state: AgentState):
    old_page = state["page"].url
    await state["page"].go_back()
    await state["page"].wait_for_load_state("domcontentloaded")

    new_page = state["page"].url
    
    return {"actions_taken": [f"I have gone back to {new_page} from {old_page}"]}



# Go To Search


async def go_to_search(state: AgentState):
    old_page = state["page"].url
    await state["page"].goto("https://www.google.com")
    await state["page"].wait_for_load_state("domcontentloaded")

    new_page = state["page"].url
    return {"actions_taken": [f"I have gone to {new_page} from {old_page}"]}



# Respond

async def respond(state: AgentState):

    text_on_page = await scrape_text(state["page"])
    system_message = """
    WebRover is an autonomous AI agent designed to browse the web, interact with pages, and complete tasks on behalf of user based on user input.
    
    Your job is to respond to the user based on the input, actions taken and the text on the page.

    You will be given the following:
    1. The user input
    2. The actions taken so far
    3. The text on the current page

    You need to respond to the user based on the input and the text on the page. Makre sure to provide response in a Markdown format.

    Provide your answer in this format:
    Response: The response you decided to give.

    Provide your answer : 

    """

    human_message = """
    User Input : {input}
    Actions taken so far : {actions_taken}
    Text on the current page: {text_on_page}
    """
    
    input = state["input"]
    actions_taken = state.get("actions_taken", "")

    messages = [SystemMessage(content=system_message), HumanMessage(content=human_message.format(input=input, actions_taken=actions_taken, text_on_page=text_on_page))]

    response = llm.invoke(messages)

    return {"response": response.content}



# Type in Text Editor

async def type_in_text_editor(state: AgentState):

        # Load the JavaScript file
        with open("marking_scripts/text_editor.js", "r", encoding="utf-8") as f:
            script = f.read()

        page = state["page"]
        print("page", page)
        # Execute JavaScript and get results
        editor_data = await page.evaluate(f"""
            (function() {{
                {script}
                return detectTextEditor();  // Calls the function from text_editor.js
            }})();
        """)

        if editor_data and "XPath" in editor_data:
            input = state["input"]
            thought = state["decide_action"]["thought"]
            conversation_history = state.get("chat_history", [])
            response = state.get("response", "")

            system_message = """
                WebRover is an autonomous AI agent designed to browse the web, interact with pages, and complete tasks on behalf of user based on user input.
                You are a helpful assistant for WebRover AI agent that can extract the content that needs to be typed in the text editor.

                You will be given the following:
                1. The user input
                2. The conversation history
                3. Editor data (xpath, x, y and if the text editor is detected, and the description of the text editor)

                Infer the content that needs to be typed in the text editor from  user input and conversation history.

                Make sure the action_type in action_element is 'type_in_text_editor'
                
            """

            human_message = """ 
            User Input : {input}
            Conversation History : {conversation_history}
            """

            messages = [SystemMessage(content=system_message), HumanMessage(content=human_message.format(input=input, conversation_history=conversation_history, editor_data=editor_data))]

            response = llm.with_structured_output(Actions).invoke(messages)
            
                 
        
            return {"actions": response, "actions_taken": [f"I have extracted the content that needs to be typed in text editor and will now proceed to type it in the text editor"]}
        else:
            print("actions_taken", "No text editor found")
            return None



# Graph 


builder =  StateGraph(AgentState)

builder.add_node("decide_immediate_action", decide_immediate_action)
builder.add_node("decide_url", decide_url)
builder.add_node("get_all_elements", get_all_elements)
builder.add_node("get_all_button_elements", get_all_button_elements)
builder.add_node("get_all_link_elements", get_all_link_elements)
builder.add_node("get_all_input_elements", get_all_input_elements)


builder.add_node("interact_with_button_elements", interact_with_button_elements)
builder.add_node("interact_with_link_elements", interact_with_link_elements)
builder.add_node("interact_with_input_elements", interact_with_input_elements)


builder.add_node("click", click)
builder.add_node("type", type)
builder.add_node("wait", wait)
builder.add_node("go_back", go_back)
builder.add_node("go_to_search", go_to_search)
builder.add_node("type_in_text_editor", type_in_text_editor)


builder.add_node("respond", respond)



builder.add_edge(START, "decide_immediate_action")
builder.add_conditional_edges("decide_immediate_action", decide_immediate_action_router, ["decide_url", "get_all_elements", "get_all_input_elements", "get_all_button_elements", "get_all_link_elements", "go_back", "go_to_search", "respond", "wait", "type_in_text_editor"])

builder.add_edge("decide_url", "decide_immediate_action")
builder.add_edge("get_all_elements", "decide_immediate_action")
builder.add_edge("get_all_input_elements", "interact_with_input_elements")
builder.add_edge("get_all_button_elements", "interact_with_button_elements")
builder.add_edge("get_all_link_elements", "interact_with_link_elements")
builder.add_edge("go_back", "decide_immediate_action")
builder.add_edge("go_to_search", "decide_immediate_action")
builder.add_edge("wait", "decide_immediate_action")
builder.add_edge("respond", END)


builder.add_edge("interact_with_input_elements", "type")
builder.add_edge("type_in_text_editor", "type")
builder.add_edge("type", "decide_immediate_action")

builder.add_edge("interact_with_button_elements", "click")
builder.add_edge("interact_with_link_elements", "click")
builder.add_edge("click","decide_immediate_action")


task_agent = builder.compile()

