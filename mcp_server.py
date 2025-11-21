import asyncio
import json
import logging
from typing import Any, Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Globals for WS connections and response queues (per session)
active_connections: Dict[str, WebSocket] = {}
response_queues: Dict[str, asyncio.Queue] = {}  # Queue for tool responses

# Create MCP with stateless_http for proxy stability
mcp = FastMCP("web-interact-server", stateless_http=True)

# Helper to send WS message and await response via queue
async def send_and_await_ws(session_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
    if session_id not in active_connections:
        raise ValueError(f"No active connection for session: {session_id}")
    ws = active_connections[session_id]
    logger.info(f"Sending to React: {message}")
    await ws.send_text(json.dumps(message))
    # Await on queue for this session
    if session_id not in response_queues:
        response_queues[session_id] = asyncio.Queue()
    queue = response_queues[session_id]
    try:
        response_text = await asyncio.wait_for(queue.get(), timeout=60.0)
        logger.info(f"Raw response text: {response_text}")
        response = json.loads(response_text)
        logger.info(f"Received from React: {response}")
        return response
    except asyncio.TimeoutError:
        logger.error("Timeout waiting for React response")
        raise TimeoutError("No response from web page within 60 seconds")
    except Exception as e:
        logger.error(f"WS communication error: {e}")
        raise RuntimeError(f"WS communication error: {e}")

# Define tools (registered on mcp)
@mcp.tool()
async def take_html_snapshot(url_or_session: str = "default") -> str:
    """Take a HTML snapshot of the connected web page.
    
    Args:
        url_or_session: Session ID for the React app (default: 'default').
    """
    try:
        message = {"type": "snapshot", "action": "capture"}
        response = await send_and_await_ws(url_or_session, message)
        if response.get("success"):
            html = response["html"]
            return f"HTML Snapshot captured successfully (length: {len(html)} chars). Preview: {html[:500]}..."
        else:
            return f"Failed to capture snapshot: {response.get('error', 'Unknown error')}"
    except Exception as e:
        logger.error(f"Snapshot error: {e}")
        return f"Error taking snapshot: {str(e)}"

@mcp.tool()
async def show_confirmation_alert(message: str, session_id: str = "default") -> bool:
    """Show a confirmation alert on the user's web page and return the result.
    
    Args:
        message: The confirmation message.
        session_id: Session ID for the React app.
    """
    try:
        ws_message = {"type": "confirm", "message": message}
        response = await send_and_await_ws(session_id, ws_message)
        confirmed = response.get("confirmed", False)
        logger.info(f"Confirmation result: {confirmed}")
        return confirmed
    except Exception as e:
        logger.error(f"Alert error: {e}")
        return False

@mcp.tool()
async def show_question_popup(question: str, session_id: str = "default") -> str:
    """Show a question popup on the web page and return the user's answer.
    
    Args:
        question: The question to ask.
        session_id: Session ID for the React app.
    """
    try:
        ws_message = {"type": "prompt", "question": question}
        response = await send_and_await_ws(session_id, ws_message)
        answer = response.get("answer", "")
        logger.info(f"Question answer: {answer}")
        return answer
    except Exception as e:
        logger.error(f"Popup error: {e}")
        return f"Error getting answer: {str(e)}"

# Custom lifespan for WS cleanup + MCP session manager init
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("MCP Server starting...")
    async with mcp.session_manager.run():  # Initializes task group/session
        yield
    # Cleanup WS connections and queues
    for session_id in list(active_connections.keys()):
        try:
            await active_connections[session_id].close()
            if session_id in response_queues:
                response_queues[session_id].put_nowait(None)  # Signal end
            del active_connections[session_id]
            if session_id in response_queues:
                del response_queues[session_id]
        except:
            pass
    logger.info("MCP Server shutting down.")

# FastAPI app with lifespan and CORS
app = FastAPI(lifespan=lifespan)
app.router.redirect_slashes = False  # Disable trailing slash redirects
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount MCP at /mcp (clients connect to /mcp/mcp)
app.mount("/mcp", mcp.streamable_http_app())

# WebSocket endpoint (non-blocking receive for responses only)
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, session_id: str = Query(default="default")):
    await websocket.accept()
    active_connections[session_id] = websocket
    response_queues[session_id] = asyncio.Queue()  # Create queue for this session
    logger.info(f"WebSocket connected for session: {session_id}")
    try:
        while True:
            # Only receive responses from React (no await in tools)
            data = await websocket.receive_text()
            response = json.loads(data)
            logger.info(f"Received from React (raw): {response}")
            # Put response in queue for the awaiting tool
            if session_id in response_queues:
                response_queues[session_id].put_nowait(data)  # Put raw text for parsing in tool
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session: {session_id}")
    except Exception as e:
        logger.error(f"WS endpoint error: {e}")
    finally:
        if session_id in active_connections:
            del active_connections[session_id]
        if session_id in response_queues:
            del response_queues[session_id]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")