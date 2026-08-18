"""WebSocket manager with real-time analysis streaming."""

import asyncio
import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from sentinel_agents.graph import analyze_log


class WSMessage(BaseModel):
    """WebSocket message protocol."""

    type: str  # log, ack, progress, result, error, ping, pong
    data: dict[str, Any] | None = None


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
        """WebSocket endpoint for real-time analysis."""
        await self.connect(websocket)

        # Start heartbeat task
        heartbeat = asyncio.create_task(self.heartbeat_task(websocket))

        try:
            while True:
                # Receive log data
                data = await websocket.receive_json()

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
