"""Real-Time Voice WebSocket Gateway

Provides full-duplex bidirectional streaming for voice interactions:
- Connect & session binding
- Audio streaming / chunking (speech frames)
- Speech event signaling (SPEECH_STARTED, SPEECH_ENDED)
- Real-time barge-in / interruption detection & turn progression
- In-flight background task cancellation via CancellationManager
- Pre-send turn validation (stale-event & stale-audio rejection)
- Disconnect teardown with zero leaked tasks

Core Invariant:
"Cancellation is best-effort; stale-result rejection is the correctness guarantee."

DataForge 2026 Rime Hackathon - Phase 14
"""

import asyncio
import base64
import json
import logging
import time
from typing import Any, Dict, Optional, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from backend.app.core.session import SessionStore, VoiceSession, default_session_store
from backend.app.core.cancellation import CancellationManager, default_cancellation_manager
from backend.app.services.voice_agent import (
    VoiceAgentOrchestrator,
    VoiceAgentStaleTurnError,
    VoiceAgentOrchestrationError,
    default_voice_agent,
)
from backend.app.services.conversation import (
    ConversationManager,
    default_conversation_manager,
    SessionNotFoundError,
    SessionClosedError,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Real-Time Voice WebSocket"])


class WebSocketEventType:
    """Standardized event types for bidirectional WebSocket messaging."""
    # Lifecycle
    CONNECT = "CONNECT"
    CONNECT_ACK = "CONNECT_ACK"
    DISCONNECT = "DISCONNECT"
    ERROR = "ERROR"

    # Speech & Audio Input
    SPEECH_STARTED = "SPEECH_STARTED"
    AUDIO_DATA = "AUDIO_DATA"
    AUDIO_CHUNK = "AUDIO_CHUNK"
    SPEECH_ENDED = "SPEECH_ENDED"
    TEXT_PROMPT = "TEXT_PROMPT"

    # Interruption & Turn Lifecycle
    INTERRUPTION_DETECTED = "INTERRUPTION_DETECTED"
    TURN_STARTED = "TURN_STARTED"
    TURN_INTERRUPTED = "TURN_INTERRUPTED"
    TURN_CANCELLED = "TURN_CANCELLED"
    TURN_COMPLETED = "TURN_COMPLETED"

    # Assistant Output Progression
    TRANSCRIPT = "TRANSCRIPT"
    THINKING = "THINKING"
    AUDIO_STARTED = "AUDIO_STARTED"
    AUDIO_STOP = "AUDIO_STOP"


class VoiceWebSocketManager:
    """Manages active WebSocket connections indexed by session_id with multi-session isolation."""

    def __init__(
        self,
        session_store: Optional[SessionStore] = None,
        cancellation_manager: Optional[CancellationManager] = None,
        conversation_manager: Optional[ConversationManager] = None,
        orchestrator: Optional[VoiceAgentOrchestrator] = None,
    ):
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._store: SessionStore = session_store or default_session_store
        self._cancellation: CancellationManager = (
            cancellation_manager or default_cancellation_manager
        )
        self._conversation: ConversationManager = (
            conversation_manager or default_conversation_manager
        )
        self._orchestrator: VoiceAgentOrchestrator = (
            orchestrator or default_voice_agent
        )
        self._audio_buffers: Dict[str, bytearray] = {}  # Audio accumulator per session

    async def connect(self, websocket: WebSocket, session_id: str) -> VoiceSession:
        """Accept WebSocket connection and bind to session."""
        await websocket.accept()
        session = self._store.get_or_create_session(session_id=session_id)
        current_id = session.session_id

        if current_id not in self._connections:
            self._connections[current_id] = set()
        self._connections[current_id].add(websocket)
        self._audio_buffers[current_id] = bytearray()

        # Send ACK
        await self.send_event(
            websocket=websocket,
            session_id=current_id,
            turn_id=session.active_turn_id,
            event_type=WebSocketEventType.CONNECT_ACK,
            data={
                "session_id": current_id,
                "active_turn_id": session.active_turn_id,
                "status": "connected",
                "timestamp_ms": int(time.time() * 1000),
            },
        )
        return session

    def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        """Remove connection and cancel owned background tasks."""
        if session_id in self._connections:
            self._connections[session_id].discard(websocket)
            if not self._connections[session_id]:
                del self._connections[session_id]
        if session_id in self._audio_buffers:
            del self._audio_buffers[session_id]

        # Cancel all in-flight tasks for the disconnected session
        self._cancellation.cancel_all_session_tasks(session_id=session_id, reason="ws_disconnect")

    async def send_event(
        self,
        websocket: WebSocket,
        session_id: str,
        turn_id: int,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
        validate_turn: bool = False,
    ) -> bool:
        """Send structured JSON event to client with optional turn validation gate.
        
        If validate_turn is True, drops event if turn_id is not currently active.
        """
        if validate_turn and turn_id > 0:
            session = self._store.get_session(session_id)
            if not session or not session.validate_turn(turn_id):
                logger.debug(f"Dropping stale event {event_type} for turn {turn_id} (session {session_id})")
                return False

        payload = {
            "event_type": event_type,
            "session_id": session_id,
            "turn_id": turn_id,
            "timestamp_ms": int(time.time() * 1000),
            "data": data or {},
        }
        try:
            await websocket.send_text(json.dumps(payload))
            return True
        except Exception as e:
            logger.warning(f"Failed to send event {event_type} to session {session_id}: {e}")
            return False

    async def broadcast_session_event(
        self,
        session_id: str,
        turn_id: int,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
        validate_turn: bool = False,
    ) -> int:
        """Broadcast event to all open WebSockets for a session."""
        sockets = list(self._connections.get(session_id, []))
        sent_count = 0
        for ws in sockets:
            ok = await self.send_event(
                websocket=ws,
                session_id=session_id,
                turn_id=turn_id,
                event_type=event_type,
                data=data,
                validate_turn=validate_turn,
            )
            if ok:
                sent_count += 1
        return sent_count

    async def handle_message(
        self,
        websocket: WebSocket,
        session_id: str,
        raw_message: Any,
    ) -> None:
        """Process an inbound client message (JSON or binary audio frames)."""
        session = self._store.get_session(session_id)
        if not session:
            await self.send_event(
                websocket=websocket,
                session_id=session_id,
                turn_id=0,
                event_type=WebSocketEventType.ERROR,
                data={"error": f"Session '{session_id}' not found."},
            )
            return

        if isinstance(raw_message, bytes):
            # Binary audio chunk
            if session_id in self._audio_buffers:
                self._audio_buffers[session_id].extend(raw_message)
            return

        # JSON text payload
        try:
            msg = json.loads(raw_message)
            if not isinstance(msg, dict):
                raise ValueError("Message must be a JSON object.")
        except Exception as exc:
            await self.send_event(
                websocket=websocket,
                session_id=session_id,
                turn_id=session.active_turn_id,
                event_type=WebSocketEventType.ERROR,
                data={"error": f"Invalid JSON payload: {str(exc)}"},
            )
            return

        event_type = msg.get("event_type", "").upper()
        event_turn_id = msg.get("turn_id", session.active_turn_id)
        event_data = msg.get("data", {})

        # -------------------------------------------------------------
        # 1. SPEECH_STARTED / AUDIO_START
        # -------------------------------------------------------------
        if event_type in (WebSocketEventType.SPEECH_STARTED, "AUDIO_START"):
            # Clear audio accumulator buffer for fresh utterance
            self._audio_buffers[session_id] = bytearray()
            # If assistant was active, handle barge-in advance
            if session.active_turn_id > 0:
                active_turn = session.get_active_turn()
                if active_turn and active_turn.status == "active":
                    # Check if there is an in-flight assistant task running
                    active_tasks = self._cancellation.get_active_tasks(session_id, session.active_turn_id)
                    if active_tasks:
                        await self._process_interruption(
                            websocket=websocket,
                            session_id=session_id,
                            reason=event_data.get("reason", "speech_started_barge_in"),
                            detection_source=event_data.get("detection_source", "vad"),
                        )
                        return

            await self.send_event(
                websocket=websocket,
                session_id=session_id,
                turn_id=session.active_turn_id,
                event_type=WebSocketEventType.SPEECH_STARTED,
                data={"status": "listening", "turn_id": session.active_turn_id},
            )

        # -------------------------------------------------------------
        # 2. AUDIO_DATA / AUDIO_CHUNK
        # -------------------------------------------------------------
        elif event_type in (WebSocketEventType.AUDIO_DATA, WebSocketEventType.AUDIO_CHUNK):
            chunk_b64 = event_data.get("audio_bytes_b64") or event_data.get("data")
            if chunk_b64:
                try:
                    chunk_bytes = base64.b64decode(chunk_b64)
                    if session_id in self._audio_buffers:
                        self._audio_buffers[session_id].extend(chunk_bytes)
                except Exception as e:
                    logger.warning(f"Failed to decode base64 audio chunk: {e}")

        # -------------------------------------------------------------
        # 3. INTERRUPTION_DETECTED / BARGE-IN
        # -------------------------------------------------------------
        elif event_type in (WebSocketEventType.INTERRUPTION_DETECTED, "BARGE_IN"):
            await self._process_interruption(
                websocket=websocket,
                session_id=session_id,
                reason=event_data.get("reason", "barge_in"),
                detection_source=event_data.get("detection_source", "vad"),
                assistant_state=event_data.get("assistant_state"),
            )

        # -------------------------------------------------------------
        # 4. SPEECH_ENDED / AUDIO_END -> Trigger Full Voice Pipeline
        # -------------------------------------------------------------
        elif event_type in (WebSocketEventType.SPEECH_ENDED, "AUDIO_END"):
            audio_accum = bytes(self._audio_buffers.get(session_id, b""))
            self._audio_buffers[session_id] = bytearray()  # Reset buffer

            # Create or advance active turn
            new_turn_id = self._conversation.create_turn(session_id)
            await self.send_event(
                websocket=websocket,
                session_id=session_id,
                turn_id=new_turn_id,
                event_type=WebSocketEventType.TURN_STARTED,
                data={"turn_id": new_turn_id},
            )

            # Spawn async pipeline task
            task = asyncio.create_task(
                self._run_voice_pipeline_task(
                    websocket=websocket,
                    session_id=session_id,
                    turn_id=new_turn_id,
                    audio_bytes=audio_accum if len(audio_accum) > 0 else None,
                    text_prompt=event_data.get("prompt"),
                    speaker=event_data.get("speaker"),
                    model_id=event_data.get("model_id"),
                )
            )
            self._cancellation.register_task(
                session_id=session_id,
                turn_id=new_turn_id,
                task=task,
                task_type="ws_turn_pipeline",
            )

        # -------------------------------------------------------------
        # 5. TEXT_PROMPT -> Text-driven Pipeline
        # -------------------------------------------------------------
        elif event_type == WebSocketEventType.TEXT_PROMPT:
            prompt_text = event_data.get("text", "").strip()
            if not prompt_text:
                await self.send_event(
                    websocket=websocket,
                    session_id=session_id,
                    turn_id=session.active_turn_id,
                    event_type=WebSocketEventType.ERROR,
                    data={"error": "Text prompt cannot be empty."},
                )
                return

            new_turn_id = self._conversation.create_turn(session_id, prompt=prompt_text)
            await self.send_event(
                websocket=websocket,
                session_id=session_id,
                turn_id=new_turn_id,
                event_type=WebSocketEventType.TURN_STARTED,
                data={"turn_id": new_turn_id, "prompt": prompt_text},
            )

            task = asyncio.create_task(
                self._run_voice_pipeline_task(
                    websocket=websocket,
                    session_id=session_id,
                    turn_id=new_turn_id,
                    audio_bytes=None,
                    text_prompt=prompt_text,
                    speaker=event_data.get("speaker"),
                    model_id=event_data.get("model_id"),
                )
            )
            self._cancellation.register_task(
                session_id=session_id,
                turn_id=new_turn_id,
                task=task,
                task_type="ws_turn_pipeline",
            )

        # -------------------------------------------------------------
        # 6. DISCONNECT
        # -------------------------------------------------------------
        elif event_type == WebSocketEventType.DISCONNECT:
            self.disconnect(websocket, session_id)
            await websocket.close()

        else:
            await self.send_event(
                websocket=websocket,
                session_id=session_id,
                turn_id=session.active_turn_id,
                event_type=WebSocketEventType.ERROR,
                data={"error": f"Unknown event_type: '{event_type}'"},
            )

    async def _process_interruption(
        self,
        websocket: WebSocket,
        session_id: str,
        reason: str = "barge_in",
        detection_source: str = "vad",
        assistant_state: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Atomically advance turn, cancel obsolete tasks, and notify client with AUDIO_STOP."""
        session = self._store.get_session(session_id)
        if not session:
            return {}

        result = self._conversation.interrupt_and_advance_turn(
            session_id=session_id,
            reason=reason,
            detection_source=detection_source,
            assistant_state=assistant_state,
        )
        prev_id = result["previous_turn_id"]
        new_id = result["new_turn_id"]

        # Send AUDIO_STOP immediately to halt active playback
        await self.send_event(
            websocket=websocket,
            session_id=session_id,
            turn_id=prev_id,
            event_type=WebSocketEventType.AUDIO_STOP,
            data={
                "interrupted_turn_id": prev_id,
                "new_turn_id": new_id,
                "reason": reason,
            },
        )

        # Send TURN_INTERRUPTED event
        await self.send_event(
            websocket=websocket,
            session_id=session_id,
            turn_id=new_id,
            event_type=WebSocketEventType.TURN_INTERRUPTED,
            data=result,
        )
        return result

    async def _run_voice_pipeline_task(
        self,
        websocket: WebSocket,
        session_id: str,
        turn_id: int,
        audio_bytes: Optional[bytes] = None,
        text_prompt: Optional[str] = None,
        speaker: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> None:
        """Asynchronous execution task running STT -> LLM -> TTS pipeline for turn."""
        session = self._store.get_session(session_id)
        if not session:
            return

        try:
            # 1. Pre-turn validation check
            if not session.validate_turn(turn_id):
                logger.info(f"Turn {turn_id} superseded before pipeline execution started.")
                return

            # Signal THINKING / TRANSCRIBING
            if audio_bytes and len(audio_bytes) > 0:
                await self.send_event(
                    websocket=websocket,
                    session_id=session_id,
                    turn_id=turn_id,
                    event_type=WebSocketEventType.TRANSCRIPT,
                    data={"status": "transcribing", "is_final": False},
                    validate_turn=True,
                )
            else:
                await self.send_event(
                    websocket=websocket,
                    session_id=session_id,
                    turn_id=turn_id,
                    event_type=WebSocketEventType.THINKING,
                    data={"status": "thinking"},
                    validate_turn=True,
                )

            # Execute pipeline
            result = await self._orchestrator.process_turn(
                session_id=session_id,
                turn_id=turn_id,
                audio_bytes=audio_bytes,
                text_prompt=text_prompt,
                speaker=speaker,
                model_id=model_id,
            )

            # 2. Post-execution validation gate (rejection of superseded turns)
            if not session.validate_turn(turn_id):
                logger.info(f"Turn {turn_id} superseded during pipeline execution. Dropping outputs.")
                return

            # Send user transcript
            await self.send_event(
                websocket=websocket,
                session_id=session_id,
                turn_id=turn_id,
                event_type=WebSocketEventType.TRANSCRIPT,
                data={
                    "transcript": result.user_prompt,
                    "is_final": True,
                },
                validate_turn=True,
            )

            # Send AUDIO_STARTED metadata
            await self.send_event(
                websocket=websocket,
                session_id=session_id,
                turn_id=turn_id,
                event_type=WebSocketEventType.AUDIO_STARTED,
                data={
                    "response": result.final_response,
                    "final_response": result.final_response,
                    "assistant_text": result.final_response,
                    "speaker": result.tts_metadata.speaker,
                    "model_id": result.tts_metadata.model_id,
                    "format": result.tts_metadata.audio_format,
                    "bytes_length": len(result.audio_bytes),
                    "latency_ms": result.latency_ms,
                },
                validate_turn=True,
            )

            # Send binary/base64 AUDIO_DATA payload
            audio_b64 = base64.b64encode(result.audio_bytes).decode("utf-8")
            await self.send_event(
                websocket=websocket,
                session_id=session_id,
                turn_id=turn_id,
                event_type=WebSocketEventType.AUDIO_DATA,
                data={
                    "audio_b64": audio_b64,
                    "format": result.tts_metadata.audio_format,
                    "speaker": result.tts_metadata.speaker,
                    "model_id": result.tts_metadata.model_id,
                    "bytes_length": len(result.audio_bytes),
                },
                validate_turn=True,
            )

            # Send TURN_COMPLETED
            await self.send_event(
                websocket=websocket,
                session_id=session_id,
                turn_id=turn_id,
                event_type=WebSocketEventType.TURN_COMPLETED,
                data={
                    "type": "TURN_COMPLETED",
                    "turn_id": turn_id,
                    "response": result.final_response,
                    "final_response": result.final_response,
                    "assistant_response": result.final_response,
                    "user_prompt": result.user_prompt,
                    "latency_ms": result.latency_ms,
                    "status": "completed",
                },
                validate_turn=True,
            )

        except asyncio.CancelledError:
            # Clean task cancellation: do not send error or mutate state
            logger.info(f"WebSocket turn pipeline for turn {turn_id} (session {session_id}) cancelled cleanly.")
            await self.send_event(
                websocket=websocket,
                session_id=session_id,
                turn_id=turn_id,
                event_type=WebSocketEventType.TURN_CANCELLED,
                data={"turn_id": turn_id, "reason": "turn_superseded_or_cancelled"},
                validate_turn=False,
            )
            raise
        except VoiceAgentStaleTurnError as exc:
            logger.info(f"Stale turn error caught in WebSocket pipeline: {exc}. Dropping output.")
        except VoiceAgentOrchestrationError as exc:
            # Valid turn failure: send error
            if session.validate_turn(turn_id):
                await self.send_event(
                    websocket=websocket,
                    session_id=session_id,
                    turn_id=turn_id,
                    event_type=WebSocketEventType.ERROR,
                    data={"error": str(exc), "status_code": exc.status_code},
                )
        except Exception as exc:
            if session.validate_turn(turn_id):
                await self.send_event(
                    websocket=websocket,
                    session_id=session_id,
                    turn_id=turn_id,
                    event_type=WebSocketEventType.ERROR,
                    data={"error": f"Internal pipeline error: {str(exc)}"},
                )


# Global WebSocket Manager singleton
default_ws_manager = VoiceWebSocketManager()


# =====================================================================
# WebSocket Endpoints
# =====================================================================

@router.websocket("/voice/ws/{session_id}")
async def voice_websocket_session_endpoint(websocket: WebSocket, session_id: str):
    """Full-duplex real-time voice interaction WebSocket bound to specific session_id."""
    session = await default_ws_manager.connect(websocket, session_id=session_id)
    try:
        while True:
            # Support both text JSON events and binary frames
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if "text" in message:
                await default_ws_manager.handle_message(
                    websocket=websocket,
                    session_id=session.session_id,
                    raw_message=message["text"],
                )
            elif "bytes" in message:
                await default_ws_manager.handle_message(
                    websocket=websocket,
                    session_id=session.session_id,
                    raw_message=message["bytes"],
                )
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception as e:
        logger.warning(f"WebSocket session {session_id} error: {e}")
    finally:
        default_ws_manager.disconnect(websocket, session_id=session.session_id)


@router.websocket("/voice/ws")
async def voice_websocket_auto_session_endpoint(websocket: WebSocket):
    """Full-duplex real-time voice interaction WebSocket with auto-generated session_id."""
    # Generate auto session
    session = default_session_store.get_or_create_session()
    await voice_websocket_session_endpoint(websocket, session_id=session.session_id)
