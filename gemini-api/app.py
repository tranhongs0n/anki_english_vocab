import os
import uuid
import io
import shutil
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Depends, Header, HTTPException, Body, UploadFile, File, Form
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import orjson as json

from gemini_webapi import GeminiClient, ChatSession, AvailableModel, set_log_level, logger
from gemini_webapi.constants import Model
from gemini_webapi.exceptions import AuthError, GeminiError, APIError
from gemini_webapi.types import ChatHistory, ChatInfo, ModelOutput

app = FastAPI(
    title="Gemini WebAPI REST Server",
    description="REST API wrapper for HanaokaYuzu's Gemini-API wrapper",
    version="1.0.0"
)

# Enable CORS for local/external web interface access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure temp directory exists for uploads
TEMP_DIR = Path("./temp_uploads")
TEMP_DIR.mkdir(exist_ok=True)

# Session memory store
class ClientSession:
    def __init__(self, client: GeminiClient):
        self.client = client
        self.chats: Dict[str, ChatSession] = {}
        self.created_at = asyncio.get_event_loop().time()

sessions: Dict[str, ClientSession] = {}
default_session_id: Optional[str] = None

# Helper functions to convert objects to dict
def serialize_model_output(output: ModelOutput) -> dict:
    # Explicitly serialize properties which aren't in model_dump()
    return {
        "metadata": output.metadata,
        "chosen": output.chosen,
        "rcid": output.rcid,
        "text": output.text,
        "text_delta": output.text_delta or "",
        "thoughts": output.thoughts,
        "thoughts_delta": output.thoughts_delta or "",
        "images": [
            {
                "url": img.url,
                "title": img.title,
                "alt": img.alt
            }
            for img in output.images
        ] if output.images else [],
        "videos": [
            {
                "url": v.url,
                "title": v.title
            }
            for v in output.videos
        ] if hasattr(output, "videos") and output.videos else [],
        "media": [
            {
                "url": m.url,
                "title": m.title
            }
            for m in output.media
        ] if hasattr(output, "media") and output.media else [],
        "deep_research_plan": {
            "cid": output.deep_research_plan.cid,
            "title": output.deep_research_plan.title,
            "eta_text": output.deep_research_plan.eta_text,
            "steps": output.deep_research_plan.steps
        } if output.deep_research_plan else None
    }

def serialize_chat_history(history: ChatHistory) -> dict:
    return {
        "cid": history.cid,
        "turns": [
            {
                "role": turn.role,
                "text": turn.text,
                "model_output": serialize_model_output(turn.model_output) if turn.model_output else None
            }
            for turn in history.turns
        ]
    }

def get_model_from_str(client: GeminiClient, model_str: Optional[str]) -> Model | AvailableModel | str:
    if not model_str or model_str == "unspecified":
        return Model.UNSPECIFIED
    try:
        return Model.from_name(model_str)
    except ValueError:
        if client:
            if model_str in client._model_registry:
                return client._model_registry[model_str]
            # Check if model_str looks like a hex model ID
            if len(model_str) == 16 and all(c in "0123456789abcdefABCDEF" for c in model_str):
                logger.info(f"Dynamically registering unknown model ID: {model_str}")
                try:
                    model = AvailableModel(
                        model_id=model_str,
                        model_name="",
                        display_name="Dynamic Model",
                        description="Dynamically registered model",
                        capacity=1,
                        capacity_field=12
                    )
                    client._model_registry[model_str] = model
                    return model
                except Exception as e:
                    logger.error(f"Failed to dynamically register model: {e}")
        return model_str

# Dependency injection for getting the right client
async def get_active_client(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    x_secure_1psid: Optional[str] = Header(None, alias="X-Secure-1PSID"),
    x_secure_1psidts: Optional[str] = Header(None, alias="X-Secure-1PSIDTS")
) -> GeminiClient:
    global default_session_id

    # 1. Look up by provided session_id
    if x_session_id and x_session_id in sessions:
        return sessions[x_session_id].client

    # 2. Look up by header cookies on-the-fly
    if x_secure_1psid:
        # Check if we have a session with these cookies
        for sid, sess in list(sessions.items()):
            try:
                psid = sess.client.cookies.get("__Secure-1PSID")
                if psid == x_secure_1psid:
                    return sess.client
            except Exception:
                pass
        
        # None found, initialize new client on the fly
        logger.info("Initializing new client session from headers...")
        client = GeminiClient(
            secure_1psid=x_secure_1psid,
            secure_1psidts=x_secure_1psidts or ""
        )
        await client.init(auto_refresh=True)
        session_id = uuid.uuid4().hex
        sessions[session_id] = ClientSession(client)
        return client

    # 3. Fallback to default session if initialized
    if default_session_id and default_session_id in sessions:
        return sessions[default_session_id].client

    # 3.5. Fallback to any active session (e.g. created via web UI)
    if sessions:
        last_session_id = list(sessions.keys())[-1]
        return sessions[last_session_id].client

    # 4. Try loading from environment variables on the fly if not initialized yet
    env_psid = os.getenv("GEMINI_SECURE_1PSID")
    env_psidts = os.getenv("GEMINI_SECURE_1PSIDTS")
    if env_psid:
        logger.info("Initializing default client session from env vars...")
        try:
            client = GeminiClient(
                secure_1psid=env_psid,
                secure_1psidts=env_psidts or ""
            )
            await client.init(auto_refresh=True)
            default_session_id = uuid.uuid4().hex
            sessions[default_session_id] = ClientSession(client)
            return client
        except Exception as e:
            logger.error(f"Failed to auto-init default client from env: {e}")

    raise HTTPException(
        status_code=401,
        detail="Unauthorized: No active session or valid credentials found. Please initialize a session first."
    )

COOKIE_FILE = Path("./session_cookies.json")

def save_session_cookies(client: GeminiClient):
    try:
        psid = client.cookies.get("__Secure-1PSID")
        psidts = client.cookies.get("__Secure-1PSIDTS")
        if psid:
            data = {"__Secure-1PSID": psid, "__Secure-1PSIDTS": psidts or ""}
            COOKIE_FILE.write_text(json.dumps(data).decode('utf-8'), encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to save cookies: {e}")

async def save_cookies_loop(client: GeminiClient):
    while True:
        await asyncio.sleep(60)
        try:
            psid = client.cookies.get("__Secure-1PSID")
            psidts = client.cookies.get("__Secure-1PSIDTS")
            if psid:
                data = {"__Secure-1PSID": psid, "__Secure-1PSIDTS": psidts or ""}
                COOKIE_FILE.write_text(json.dumps(data).decode('utf-8'), encoding="utf-8")
        except Exception:
            pass

# Setup default session on startup if cookies are in environment or file
@app.on_event("startup")
async def startup_event():
    global default_session_id
    set_log_level("INFO")
    
    psid = None
    psidts = ""
    
    if COOKIE_FILE.exists():
        try:
            saved = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
            psid = saved.get("__Secure-1PSID")
            psidts = saved.get("__Secure-1PSIDTS", "")
            if psid:
                logger.info("Found saved session cookies. Initializing default session...")
        except Exception as e:
            logger.error(f"Failed to load saved cookies: {e}")
            
    if not psid:
        psid = os.getenv("GEMINI_SECURE_1PSID")
        psidts = os.getenv("GEMINI_SECURE_1PSIDTS") or ""
        if psid:
            logger.info("Found credentials in environment variables. Setting up default session...")
            
    if psid:
        try:
            client = GeminiClient(
                secure_1psid=psid,
                secure_1psidts=psidts
            )
            await client.init(auto_refresh=True)
            default_session_id = uuid.uuid4().hex
            sessions[default_session_id] = ClientSession(client)
            asyncio.create_task(save_cookies_loop(client))
            logger.success(f"Default session auto-initialized with ID: {default_session_id}")
        except Exception as e:
            logger.error(f"Failed to auto-initialize default session: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down API. Closing client sessions...")
    for session_id, sess in list(sessions.items()):
        try:
            await sess.client.close()
        except Exception:
            pass
    # Clean up temp uploads
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR, ignore_errors=True)

# ----------------- ENDPOINTS -----------------

@app.get("/", response_class=HTMLResponse)
async def serve_playground():
    index_path = Path("./index.html")
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Gemini WebAPI Server running</h1><p>index.html not found. Place index.html in directory.</p>")

@app.get("/api/session/status")
async def get_session_status(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    global default_session_id
    
    # 1. Try provided session ID
    if x_session_id and x_session_id in sessions:
        sess = sessions[x_session_id]
        return {
            "status": "authenticated",
            "session_id": x_session_id,
            "account_status": sess.client.account_status.name,
            "account_description": sess.client.account_status.description,
            "is_default": x_session_id == default_session_id
        }
        
    # 2. Try default session ID
    if default_session_id and default_session_id in sessions:
        sess = sessions[default_session_id]
        return {
            "status": "authenticated",
            "session_id": default_session_id,
            "account_status": sess.client.account_status.name,
            "account_description": sess.client.account_status.description,
            "is_default": True
        }
    
    return {
        "status": "unauthenticated",
        "session_id": None,
        "is_default": False
    }

class SessionInitRequest(BaseModel):
    secure_1psid: str
    secure_1psidts: Optional[str] = ""
    proxy: Optional[str] = None

@app.post("/api/session/init")
async def init_session(req: SessionInitRequest):
    try:
        client = GeminiClient(
            secure_1psid=req.secure_1psid,
            secure_1psidts=req.secure_1psidts or "",
            proxy=req.proxy
        )
        await client.init(auto_refresh=True)
        session_id = uuid.uuid4().hex
        # Save cookies immediately and spawn auto-save loop
        save_session_cookies(client)
        asyncio.create_task(save_cookies_loop(client))
        
        return {
            "status": "success",
            "session_id": session_id,
            "account_status": client.account_status.name,
            "account_description": client.account_status.description
        }
    except AuthError as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Initialization error: {str(e)}")

@app.get("/api/models")
async def list_models(client: GeminiClient = Depends(get_active_client)):
    # Predefined models
    predefined = [
        {"name": m.model_name, "value": m.model_name, "advanced_only": m.advanced_only}
        for m in Model if m != Model.UNSPECIFIED
    ]
    
    # Registered models fetched from RPC
    registered = []
    if client and hasattr(client, "_model_registry"):
        for k, v in client._model_registry.items():
            registered.append({
                "name": v.display_name or k,
                "value": k,
                "advanced_only": False
            })
            
    return {
        "predefined": predefined,
        "registered": registered
    }

@app.get("/api/chats")
async def list_chats(client: GeminiClient = Depends(get_active_client)):
    try:
        chats = client.list_chats()
        if chats is None:
            return []
        return [
            {
                "cid": c.cid,
                "title": c.title,
                "is_pinned": c.is_pinned,
                "timestamp": c.timestamp
            }
            for c in chats
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch chats: {str(e)}")

@app.get("/api/chats/{chat_id}")
async def get_chat_history(
    chat_id: str,
    limit: int = 20,
    client: GeminiClient = Depends(get_active_client)
):
    try:
        history = await client.read_chat(chat_id, limit=limit)
        if not history:
            return {"cid": chat_id, "turns": []}
        return serialize_chat_history(history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read chat: {str(e)}")

@app.delete("/api/chats/{chat_id}")
async def delete_chat(
    chat_id: str,
    client: GeminiClient = Depends(get_active_client)
):
    try:
        await client.delete_chat(chat_id)
        return {"status": "success", "detail": f"Chat {chat_id} deleted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete chat: {str(e)}")

# Generation endpoints

@app.post("/api/generate")
async def generate_content(
    prompt: str = Form(...),
    model: Optional[str] = Form(None),
    temporary: bool = Form(False),
    files: Optional[List[UploadFile]] = File(None),
    client: GeminiClient = Depends(get_active_client)
):
    saved_paths = []
    try:
        if files:
            for file in files:
                ext = Path(file.filename).suffix
                temp_filename = f"{uuid.uuid4().hex}{ext}"
                dest_path = TEMP_DIR / temp_filename
                with dest_path.open("wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                saved_paths.append(str(dest_path.resolve()))

        selected_model = get_model_from_str(client, model)
        
        output = await client.generate_content(
            prompt=prompt,
            files=saved_paths or None,
            model=selected_model,
            temporary=temporary
        )
        
        return serialize_model_output(output)
    except Exception as e:
        logger.exception("Generation error")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for path in saved_paths:
            try:
                os.remove(path)
            except Exception:
                pass

@app.post("/api/generate/stream")
async def generate_content_stream(
    prompt: str = Form(...),
    model: Optional[str] = Form(None),
    temporary: bool = Form(False),
    files: Optional[List[UploadFile]] = File(None),
    client: GeminiClient = Depends(get_active_client)
):
    saved_paths = []
    if files:
        for file in files:
            ext = Path(file.filename).suffix
            temp_filename = f"{uuid.uuid4().hex}{ext}"
            dest_path = TEMP_DIR / temp_filename
            with dest_path.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            saved_paths.append(str(dest_path.resolve()))

    selected_model = get_model_from_str(client, model)

    async def event_generator():
        try:
            async for chunk in client.generate_content_stream(
                prompt=prompt,
                files=saved_paths or None,
                model=selected_model,
                temporary=temporary
            ):
                data = {
                    "text_delta": chunk.text_delta,
                    "thoughts_delta": chunk.thoughts_delta,
                    "done": False
                }
                yield f"data: {json.dumps(data).decode('utf-8')}\n\n"
        except Exception as e:
            logger.exception("Streaming generation error")
            yield f"data: {json.dumps({'error': str(e)}).decode('utf-8')}\n\n"
        finally:
            for path in saved_paths:
                try:
                    os.remove(path)
                except Exception:
                    pass
            yield "data: {\"done\": true}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# Multi-turn chat session endpoints

def get_or_create_chat_session(
    client: GeminiClient, 
    chat_id: str, 
    model: Optional[str] = None
) -> ChatSession:
    sess = None
    for s in sessions.values():
        if s.client == client:
            sess = s
            break
            
    if not sess:
        sess = ClientSession(client)
        sessions[uuid.uuid4().hex] = sess
        
    if chat_id in sess.chats:
        return sess.chats[chat_id]
        
    selected_model = get_model_from_str(client, model)
    chat = client.start_chat(cid=chat_id, model=selected_model)
    sess.chats[chat_id] = chat
    return chat

class ChatSendRequest(BaseModel):
    prompt: str
    model: Optional[str] = None

@app.post("/api/chats/{chat_id}/send")
async def send_chat_message(
    chat_id: str,
    req: ChatSendRequest,
    client: GeminiClient = Depends(get_active_client)
):
    try:
        chat = None
        sess = None
        for s in sessions.values():
            if s.client == client:
                sess = s
                break
                
        if sess and chat_id not in sess.chats:
            latest = await client.fetch_latest_chat_response(chat_id)
            if latest:
                selected_model = get_model_from_str(client, req.model)
                chat = client.start_chat(
                    metadata=list(latest.metadata),
                    cid=chat_id,
                    rcid=latest.rcid,
                    model=selected_model
                )
                sess.chats[chat_id] = chat

        if not chat:
            chat = get_or_create_chat_session(client, chat_id, req.model)

        output = await chat.send_message(req.prompt)
        return serialize_model_output(output)
    except Exception as e:
        logger.exception("Chat sending error")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chats/{chat_id}/send_stream")
async def send_chat_message_stream(
    chat_id: str,
    req: ChatSendRequest,
    client: GeminiClient = Depends(get_active_client)
):
    chat = None
    sess = None
    for s in sessions.values():
        if s.client == client:
            sess = s
            break
            
    if sess and chat_id not in sess.chats:
        latest = await client.fetch_latest_chat_response(chat_id)
        if latest:
            selected_model = get_model_from_str(client, req.model)
            chat = client.start_chat(
                metadata=list(latest.metadata),
                cid=chat_id,
                rcid=latest.rcid,
                model=selected_model
            )
            sess.chats[chat_id] = chat

    if not chat:
        chat = get_or_create_chat_session(client, chat_id, req.model)

    async def event_generator():
        try:
            async for chunk in chat.send_message_stream(req.prompt):
                data = {
                    "text_delta": chunk.text_delta,
                    "thoughts_delta": chunk.thoughts_delta,
                    "done": False
                }
                yield f"data: {json.dumps(data).decode('utf-8')}\n\n"
        except Exception as e:
            logger.exception("Streaming chat error")
            yield f"data: {json.dumps({'error': str(e)}).decode('utf-8')}\n\n"
        finally:
            yield "data: {\"done\": true}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# Deep Research endpoints

class DeepResearchCreateRequest(BaseModel):
    prompt: str
    model: Optional[str] = None

@app.post("/api/research/create")
async def create_research_plan(
    req: DeepResearchCreateRequest,
    client: GeminiClient = Depends(get_active_client)
):
    try:
        selected_model = get_model_from_str(client, req.model)
        plan = await client.create_deep_research_plan(
            prompt=req.prompt,
            model=selected_model
        )
        return {
            "cid": plan.cid,
            "title": plan.title,
            "eta_text": plan.eta_text,
            "steps": plan.steps
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class DeepResearchStartRequest(BaseModel):
    cid: str
    title: str
    eta_text: str
    steps: List[str]
    model: Optional[str] = None

@app.post("/api/research/start")
async def start_research(
    req: DeepResearchStartRequest,
    client: GeminiClient = Depends(get_active_client)
):
    try:
        from gemini_webapi.types import DeepResearchPlan
        plan = DeepResearchPlan(
            cid=req.cid,
            title=req.title,
            eta_text=req.eta_text,
            steps=req.steps
        )
        await client.start_deep_research(plan=plan)
        return {"status": "success", "detail": "Deep research started successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/research/status/{chat_id}")
async def get_research_status(
    chat_id: str,
    client: GeminiClient = Depends(get_active_client)
):
    try:
        latest = await client.read_chat(chat_id, limit=1)
        if latest and latest.turns and latest.turns[0].role == "model":
            return {
                "status": "done",
                "length": len(latest.turns[0].text)
            }
        return {
            "status": "in_progress"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/research/get/{chat_id}")
async def get_research_results(
    chat_id: str,
    client: GeminiClient = Depends(get_active_client)
):
    try:
        latest = await client.fetch_latest_chat_response(chat_id)
        if not latest:
            raise HTTPException(
                status_code=404, 
                detail="Research response not found. It might still be processing."
            )
        return {
            "text": latest.text,
            "metadata": latest.metadata
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
