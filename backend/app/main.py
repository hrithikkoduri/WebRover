from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
from typing import Optional, Dict, Any, Literal
from contextlib import asynccontextmanager
import json
import time
# Import necessary functions from agent files
from .task_agent import task_agent
from .research_agent import research_agent, type
from .deep_research_agent import deep_research_agent
from .browser_manager import setup_browser, cleanup_browser_session

from fastapi.middleware.cors import CORSMiddleware

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from playwright.async_api import async_playwright

app = FastAPI()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Your Next.js app URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables for browser session
browser_session = {
    "browser": None,
    "page": None
}

# Global queue for browser events
browser_events = asyncio.Queue()

class BrowserSetupRequest(BaseModel):
    url: str = "https://www.google.com"

class QueryRequest(BaseModel):
    query: str
    agent_type: Literal["task", "research", "deep_research"]

@app.post("/setup-browser")
async def setup_browser_endpoint(request: BrowserSetupRequest):
    try:
        # Clear any existing session
        if browser_session["browser"]:
            await cleanup_browser()
            
        # Setup new browser session
        if request.url == "https://www.google.com":
            print(f"Setting up browser for {request.url}")
            browser, page = await setup_browser(request.url)
        else:
            browser, page = await setup_browser(request.url)
        
        # Store session info
        browser_session.update({
            "browser": browser,
            "page": page
        })
        
        return {"status": "success", "message": "Browser setup complete"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to setup browser: {str(e)}")

@app.post("/cleanup")
async def cleanup_browser():
    try:
        if browser_session["browser"]:
            # Use the proper cleanup function
            await cleanup_browser_session(browser_session["browser"])
            
            # Clear the session
            browser_session.update({
                "browser": None,
                "page": None
            })
        
        return {"status": "success", "message": "Browser cleanup complete"}
    except Exception as e:
        print(f"Cleanup error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cleanup browser: {str(e)}")

async def emit_browser_event(event_type: str, data: Dict[str, Any]):
    await browser_events.put({
        "type": event_type,
        "data": data
    })

@app.get("/browser-events")
async def browser_events_endpoint():
    async def event_generator():
        while True:
            try:
                event = await browser_events.get()
                yield f"data: {json.dumps(event)}\n\n"
            except asyncio.CancelledError:
                break
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

async def stream_task_agent_response(query: str, page, agent_graph):
    try:
        initial_state = {
            "input": query,
            "page": page,
            "master_plan": None,
            "dom_elements": [],
            "chat_history": [],
            "decide_action": None,
            "actions_taken": [],
            "actions": None,
            "response": ""
        }
        
        async for event in agent_graph.astream(
            initial_state,
            {"recursion_limit": 400}
        ):
            try:
                # Send keepalive more frequently
                yield f"data: {{\n  \"type\": \"keepalive\",\n  \"timestamp\": {time.time()}\n}}\n\n"
                await asyncio.sleep(0.1)  # Small delay to prevent overwhelming
                
                if isinstance(event, dict):
                    if "decide_immediate_action" in event:
                        thought = event["decide_immediate_action"]["decide_action"]["thought"]
                        thought_json = json.dumps(thought, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"thought\",\n  \"content\": {thought_json}\n}}\n\n"
                    
                    if "decide_url" in event:
                        action = event["decide_url"]["actions_taken"]
                        action_json = json.dumps(action, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"action\",\n  \"content\": {action_json}\n}}\n\n"
                    
                    # Stream DOM updates
                    if any(key in event for key in ["get_all_elements", "get_all_input_elements", 
                                                  "get_all_button_elements", "get_all_link_elements"]):
                        action = event[list(event.keys())[0]]["actions_taken"]
                        action_json = json.dumps(action, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"dom_update\",\n  \"content\": {action_json}\n}}\n\n"
                    
                    # Stream interactions
                    if any(key in event for key in ["interact_with_input_elements", 
                                                  "interact_with_button_elements",
                                                  "interact_with_link_elements"]):
                        actions = event[list(event.keys())[0]]["actions"]["element_actions"]
                        actions_json = json.dumps(actions, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"interaction\",\n  \"content\": {actions_json}\n}}\n\n"
                    
                    # Stream browser actions
                    if any(key in event for key in ["click", "type", "wait", "go_back", "go_to_search"]):
                        actions = event[list(event.keys())[0]]["actions_taken"]
                        actions_json = json.dumps(actions, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"browser_action\",\n  \"content\": {actions_json}\n}}\n\n"
                    
                    if "respond" in event:
                        response = event["respond"]["response"]
                        response_json = json.dumps(response, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"final_response\",\n  \"content\": {response_json}\n}}\n\n"
                        
                    # After each event, send another keepalive
                    yield f"data: {{\n  \"type\": \"keepalive\",\n  \"timestamp\": {time.time()}\n}}\n\n"
                        
            except Exception as e:
                error_json = json.dumps(str(e), ensure_ascii=False)
                yield f"data: {{\n  \"type\": \"error\",\n  \"content\": {error_json}\n}}\n\n"
                continue  # Continue processing even if one event fails
                
    except Exception as e:
        error_json = json.dumps(str(e), ensure_ascii=False)
        yield f"data: {{\n  \"type\": \"error\",\n  \"content\": {error_json}\n}}\n\n"
    finally:
        # Ensure we have a small delay before ending
        await asyncio.sleep(0.5)
        # Send final keepalive
        yield f"data: {{\n  \"type\": \"keepalive\",\n  \"timestamp\": {time.time()}\n}}\n\n"
        # Send completion signal
        yield f"data: {{\n  \"type\": \"complete\",\n  \"content\": \"Processing completed\"\n}}\n\n"
        # Small delay before final end message
        await asyncio.sleep(0.5)
        # Send end message
        yield f"data: {{\n  \"type\": \"end\",\n  \"content\": \"Stream completed\"\n}}\n\n"

async def stream_research_agent_response(query: str, page, agent_graph):
    try:
        initial_state = {
            "input": query,
            "page": page,
            "dom_elements": [],
            "action": None,
            "actions_taken": [],
            "visited_urls": [],
            "conversation_history": [],
            "answer": "",
            "new_page": False,
            "is_pdf": False,
            "empty_dom_retries": 0
        }
        
        async for event in agent_graph.astream(
            initial_state,
            {"recursion_limit": 400}
        ):
            try:
                # Send keepalive more frequently
                yield f"data: {{\n  \"type\": \"keepalive\",\n  \"timestamp\": {time.time()}\n}}\n\n"
                
                if isinstance(event, dict):
                    # Handle LLM thoughts
                    if "llm_call_node" in event:
                        thought = event["llm_call_node"]["action"]["thought"]
                        thought_json = json.dumps(thought, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"thought\",\n  \"content\": {thought_json}\n}}\n\n"
                    
                    # Handle browser actions
                    if any(key in event for key in ["click", "type", "wait", "go_back", "go_to_search"]):
                        actions = event[list(event.keys())[0]]["actions_taken"]
                        actions_json = json.dumps(actions, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"action\",\n  \"content\": {actions_json}\n}}\n\n"
                    
                    # Handle RAG operations
                    if "web_page_rag" in event:
                        action = event["web_page_rag"]["actions_taken"]
                        action_json = json.dumps(action, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"rag_action\",\n  \"content\": {action_json}\n}}\n\n"
                    
                    # Handle self review
                    if "self_review" in event:
                        action = event["self_review"]["actions_taken"]
                        action_json = json.dumps(action, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"review\",\n  \"content\": {action_json}\n}}\n\n"
                    
                    # Handle closing tabs
                    if "close_opened_link" in event:
                        action = event["close_opened_link"]["actions_taken"]
                        action_json = json.dumps(action, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"close_tab\",\n  \"content\": {action_json}\n}}\n\n"
                    
                    # Handle final answer
                    if "answer_node" in event:
                        action = event["answer_node"]["actions_taken"]
                        action_json = json.dumps(action, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"action\",\n  \"content\": {action_json}\n}}\n\n"
                        
                        answer = event["answer_node"]["answer"]
                        answer_json = json.dumps(answer, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"final_answer\",\n  \"content\": {answer_json}\n}}\n\n"
                        
                        conversation_history = event["answer_node"]["conversation_history"]
                        history_json = json.dumps(conversation_history, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"conversation_history\",\n  \"content\": {history_json}\n}}\n\n"
                    
                    # Handle RAG store cleanup
                    if "empty_rag_store" in event:
                        action = event["empty_rag_store"]["actions_taken"]
                        action_json = json.dumps(action, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"cleanup\",\n  \"content\": {action_json}\n}}\n\n"
                        
                await asyncio.sleep(0.1)  # Small delay between events
                        
            except Exception as e:
                error_json = json.dumps(str(e), ensure_ascii=False)
                yield f"data: {{\n  \"type\": \"error\",\n  \"content\": {error_json}\n}}\n\n"
                continue
                
    except Exception as e:
        error_json = json.dumps(str(e), ensure_ascii=False)
        yield f"data: {{\n  \"type\": \"error\",\n  \"content\": {error_json}\n}}\n\n"
    finally:
        await asyncio.sleep(0.5)
        yield f"data: {{\n  \"type\": \"complete\",\n  \"content\": \"Processing completed\"\n}}\n\n"
        await asyncio.sleep(0.5)
        yield f"data: {{\n  \"type\": \"end\",\n  \"content\": \"Stream completed\"\n}}\n\n"

async def stream_deep_research_agent_response(query: str, page, agent_graph):
    try:
        initial_state = {
            "input": query,
            "page": page,
            "dom_elements": [],
            "action": None,
            "actions_taken": [],
            "visited_urls": [],
            "conversation_history": [],
            "subtopics": [],
            "subtopic_answers": [],
            "final_answer": "",
            "new_page": False,
            "is_pdf": False,
            "subtopic_status": [],
            "subtopic_to_research": "",
            "number_of_urls_visited": 0,
            "collect_more_info": False,
            "empty_dom_retries": 0
        }
        
        async for event in agent_graph.astream(
            initial_state,
            {"recursion_limit": 400}
        ):
            try:
                # Send keepalive more frequently
                yield f"data: {{\n  \"type\": \"keepalive\",\n  \"timestamp\": {time.time()}\n}}\n\n"
                
                if isinstance(event, dict):
                    # Handle topic breakdown
                    if "topic_breakdown" in event:
                        subtopics = event["topic_breakdown"]["subtopics"]
                        subtopics_json = json.dumps(subtopics, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"subtopics\",\n  \"content\": {subtopics_json}\n}}\n\n"
                    
                    # Handle LLM thoughts
                    if "llm_call_node" in event:
                        thought = event["llm_call_node"]["action"]["thought"]
                        thought_json = json.dumps(thought, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"thought\",\n  \"content\": {thought_json}\n}}\n\n"
                    
                    # Handle browser actions
                    if any(key in event for key in ["click", "type", "wait", "go_back", "go_to_search"]):
                        action = event[list(event.keys())[0]]["actions_taken"]
                        action_json = json.dumps(action, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"browser_action\",\n  \"content\": {action_json}\n}}\n\n"
                    
                    # Handle RAG operations
                    if "web_page_rag" in event:
                        action = event["web_page_rag"]["actions_taken"]
                        action_json = json.dumps(action, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"rag_action\",\n  \"content\": {action_json}\n}}\n\n"
                    
                    # Handle self review
                    if "self_review" in event:
                        action = event["self_review"]["actions_taken"]
                        action_json = json.dumps(action, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"review\",\n  \"content\": {action_json}\n}}\n\n"
                    
                    # Handle subtopic answers
                    if "subtopic_answer_node" in event:
                        action = event["subtopic_answer_node"]["actions_taken"]
                        action_json = json.dumps(action, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"subtopic_answer\",\n  \"content\": {action_json}\n}}\n\n"
                        
                        subtopic_status = event["subtopic_answer_node"]["subtopic_status"]
                        status_json = json.dumps(subtopic_status, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"subtopic_status\",\n  \"content\": {status_json}\n}}\n\n"
                    
                    # Handle closing tabs
                    if "close_opened_link" in event:
                        action = event["close_opened_link"]["actions_taken"]
                        action_json = json.dumps(action, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"close_tab\",\n  \"content\": {action_json}\n}}\n\n"
                    
                    # Handle research compilation
                    if "compile_research" in event:
                        action = event["compile_research"]["actions_taken"]
                        action_json = json.dumps(action, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"compile\",\n  \"content\": {action_json}\n}}\n\n"
                        
                        answer = event["compile_research"]["final_answer"]
                        answer_json = json.dumps(answer, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"final_answer\",\n  \"content\": {answer_json}\n}}\n\n"
                        
                        conversation_history = event["compile_research"]["conversation_history"]
                        history_json = json.dumps(conversation_history, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"conversation_history\",\n  \"content\": {history_json}\n}}\n\n"
                    
                    # Handle RAG store cleanup
                    if "empty_rag_store" in event:
                        action = event["empty_rag_store"]["actions_taken"]
                        action_json = json.dumps(action, ensure_ascii=False)
                        yield f"data: {{\n  \"type\": \"cleanup\",\n  \"content\": {action_json}\n}}\n\n"
                        
                await asyncio.sleep(0.1)  # Small delay between events
                        
            except Exception as e:
                error_json = json.dumps(str(e), ensure_ascii=False)
                yield f"data: {{\n  \"type\": \"error\",\n  \"content\": {error_json}\n}}\n\n"
                continue
                
    except Exception as e:
        error_json = json.dumps(str(e), ensure_ascii=False)
        yield f"data: {{\n  \"type\": \"error\",\n  \"content\": {error_json}\n}}\n\n"
    finally:
        await asyncio.sleep(0.5)
        yield f"data: {{\n  \"type\": \"complete\",\n  \"content\": \"Processing completed\"\n}}\n\n"
        await asyncio.sleep(0.5)
        yield f"data: {{\n  \"type\": \"end\",\n  \"content\": \"Stream completed\"\n}}\n\n"

@app.post("/query")
async def query_agent(request: QueryRequest):
    if not browser_session["page"]:
        raise HTTPException(
            status_code=400, 
            detail="Browser not initialized. Call /setup-browser first"
        )
    
    agent_graphs = {
        "task": task_agent,
        "research": research_agent,
        "deep_research": deep_research_agent
    }
    
    stream_handlers = {
        "task": stream_task_agent_response,
        "research": stream_research_agent_response,
        "deep_research": stream_deep_research_agent_response
    }
    
    return StreamingResponse(
        stream_handlers[request.agent_type](
            request.query, 
            browser_session["page"],
            agent_graphs[request.agent_type]
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Transfer-Encoding": "chunked"
        }
    )


@app.post("/api/docs/type")
async def type_in_docs(request: Request):
    try:
        if not browser_session["page"]:
            return JSONResponse(
                status_code=400,
                content={"error": "Browser not initialized. Call /setup-browser first"}
            )

        data = await request.json()
        content = data.get('content')
        
        if not content:
            return JSONResponse(
                status_code=400,
                content={"error": "Content is required"}
            )

        page = browser_session["page"]
        await page.goto('https://docs.google.com/document/create')
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(2)  # Wait for editor to be fully loaded

        # Wait for and click the editor canvas
        editor_selector = ".kix-appview-editor"
        await page.wait_for_selector(editor_selector)
        editor = await page.query_selector(editor_selector)
        
        if editor:
            bbox = await editor.bounding_box()
            if bbox:
                # Click in the middle of the editor
                x = bbox['x'] + bbox['width'] / 2
                y = bbox['y'] + bbox['height'] / 2
                
                await page.mouse.click(x, y)
                await asyncio.sleep(1)

                state = {
                    "page": page,
                    "action": {
                        "action_element": {
                            "type": "text_editor",
                            "description": "Google Docs editor",
                            "x": x,
                            "y": y,
                            "xpath": f"//div[contains(@class, 'kix-appview-editor')]",
                            "inViewport": True
                        },
                        "args": content
                    }
                }
                
                result = await type(state)
                
                return JSONResponse(
                    status_code=200,
                    content={"message": "Content typed successfully", "actions": result["actions_taken"]}
                )
        
        return JSONResponse(
            status_code=500,
            content={"error": "Text editor not found"}
        )
            
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to type content: {str(e)}"}
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
