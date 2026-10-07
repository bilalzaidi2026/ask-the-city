"""
The web app's server.

    python -m uvicorn web.server:app --port 8000
    then open http://localhost:8000

POST /api/ask streams the agent's work to the browser as it happens, using
Server-Sent Events (SSE): one line per event, "data: {...json...}", sent the moment
each step finishes. The page shows them live, then renders the final answer.
"""
import asyncio
import json
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent.agent import ask

WEB = Path(__file__).parent
MAX_QUESTION_CHARS = 300

app = FastAPI(title="Ask the City")
app.mount("/vendor", StaticFiles(directory=WEB / "vendor"), name="vendor")


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=MAX_QUESTION_CHARS)


@app.get("/")
def home():
    return FileResponse(WEB / "index.html")


@app.post("/api/ask")
async def ask_endpoint(body: Question):
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "Please type a question.")

    async def stream():
        # The agent is ordinary blocking code, so it runs in a worker thread. Each step it
        # reports is handed to the server's event loop with call_soon_threadsafe, and this
        # stream sends it to the browser immediately. (A first version used a blocking
        # queue.Queue here, and steps sat waiting until a 15-second timer woke the stream.)
        loop = asyncio.get_running_loop()
        events = asyncio.Queue()

        def emit(event):
            loop.call_soon_threadsafe(events.put_nowait, event)

        def work():
            started = time.time()
            try:
                answer, stats = ask(question, verbose=False, on_event=emit)
                emit({"type": "answer", "answer": answer, "charts": stats["charts"],
                      "stats": {"tool_calls": stats["tool_calls"],
                                "cost_usd": stats["cost_usd"],
                                "seconds": round(time.time() - started),
                                "checker": stats["final_check"],
                                "revised": stats["revised"]}})
            except Exception as err:  # never leave the page hanging
                emit({"type": "fatal", "text": f"Something went wrong: {err}"})
            finally:
                emit(None)  # end of stream

        emit({"type": "think", "text": "Reading your question and planning which data to use."})
        worker = asyncio.create_task(asyncio.to_thread(work))
        while True:
            try:
                event = await asyncio.wait_for(events.get(), timeout=15)
            except asyncio.TimeoutError:
                yield ": still working\n\n"  # keep-alive so the connection stays open
                continue
            if event is None:
                break
            yield f"data: {json.dumps(event, default=str)}\n\n"
        await worker

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
