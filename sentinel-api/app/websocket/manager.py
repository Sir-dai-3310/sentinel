"""WebSocket manager with real-time analysis streaming."""

import asyncio
import json
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from sentinel_agents.graph import analyze_log

# Per-connection message rate limit (messages per window) so an authenticated
# WS client cannot flood the analysis graph / LLM budget.
WS_MESSAGE_RATE = 30
WS_MESSAGE_WINDOW = 60.0


class WSMessage(BaseModel):
    """WebSocket message protocol."""

    type: str  # log, ack, progress, result, error, ping, pong
    data: dict[str, Any] | None = None


def _authenticate_websocket(websocket: WebSocket) -> str | None:
    """Validate the JWT on the WS handshake.

    Accepts the token via ``Authorization: Bearer <t>`` header or a
    ``?token=<t>`` query parameter (browsers cannot set WS headers).
    Returns the authenticated username, or None when authentication fails.
    """
    from app.auth.jwt import verify_token

    token = None
    auth_header = websocket.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = websocket.query_params.get("token")
    if not token:
        return None
    try:
        token_data = verify_token(token)
    except Exception:
        return None
    return token_data.sub


class ConnectionManager:
    """Manage WebSocket connections with heartbeat and reconnection support."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.heartbeat_interval = 30  # seconds

    async def connect(self, websocket: WebSocket):
        """Accept new connection."""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_message(self, message: WSMessage, websocket: WebSocket):
        """Send message to specific client."""
        try:
            await websocket.send_json(message.model_dump())
        except Exception as e:
            print(f"Error sending message: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: WSMessage):
        """Broadcast message to all clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message.model_dump())
            except Exception:
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

    async def heartbeat_task(self, websocket: WebSocket):
        """Send periodic heartbeat pings."""
        try:
            while True:
                await asyncio.sleep(self.heartbeat_interval)
                await self.send_message(WSMessage(type="ping"), websocket)
        except Exception:
            self.disconnect(websocket)

    async def websocket_endpoint(self, websocket: WebSocket):
        """WebSocket endpoint for real-time analysis.

        Requires a valid JWT (header or ``?token=`` query param) — previously
        any unauthenticated client could trigger LLM analysis at will.
        """
        username = _authenticate_websocket(websocket)
        if username is None:
            await websocket.close(code=4401, reason="authentication required")
            return

        await self.connect(websocket)

        # Start heartbeat task
        heartbeat = asyncio.create_task(self.heartbeat_task(websocket))

        # Per-connection sliding-window rate limit
        msg_times: list[float] = []

        try:
            while True:
                # Receive log data
                data = await websocket.receive_json()

                now = time.monotonic()
                msg_times = [t for t in msg_times if now - t < WS_MESSAGE_WINDOW]
                if len(msg_times) >= WS_MESSAGE_RATE:
                    await self.send_message(
                        WSMessage(
                            type="error",
                            data={"error": "rate limit exceeded, slow down"},
                        ),
                        websocket,
                    )
                    continue
                msg_times.append(now)

                if data.get("type") == "ping":
                    # Respond to client ping
                    await self.send_message(WSMessage(type="pong"), websocket)
                    continue

                if data.get("type") != "log":
                    await self.send_message(
                        WSMessage(type="error", data={"error": "Invalid message type"}),
                        websocket,
                    )
                    continue

                # Send acknowledgment
                await self.send_message(
                    WSMessage(type="ack", data={"status": "processing"}), websocket
                )

                # Stream analysis progress
                try:
                    # Stage 1: Rule engine
                    await self.send_message(
                        WSMessage(
                            type="progress",
                            data={"stage": "rule_engine", "status": "running"},
                        ),
                        websocket,
                    )

                    # Call real agent graph
                    result = await analyze_log(data.get("log", {}))

                    # Stage 2: Complete
                    await self.send_message(
                        WSMessage(
                            type="result",
                            data={
                                "verdict": result.verdict.model_dump()
                                if result.verdict
                                else None,
                                "rule_hits": [
                                    hit.model_dump() for hit in result.rule_hits
                                ],
                                "agent_trace": result.agent_trace,
                                "skipped_llm": result.skipped_llm,
                                "analysis_status": result.analysis_status,
                                "analysis_error": result.analysis_error,
                            },
                        ),
                        websocket,
                    )

                except Exception as e:
                    await self.send_message(
                        WSMessage(type="error", data={"error": str(e)}), websocket
                    )

        except WebSocketDisconnect:
            self.disconnect(websocket)
        except Exception as e:
            print(f"WebSocket error: {e}")
            self.disconnect(websocket)
        finally:
            heartbeat.cancel()


manager = ConnectionManager()
