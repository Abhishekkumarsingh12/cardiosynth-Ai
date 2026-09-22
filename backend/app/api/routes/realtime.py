from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter
from fastapi import WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.database import SessionLocal
from app.models import ECGAnalysis, ECGUpload, User
from app.services.ecg_stream_service import build_stream_source, stream_signal_chunks


router = APIRouter()
ws_router = APIRouter()


def _auth_user_from_token(token: str) -> Optional[User]:
    sub = decode_token(token)
    if sub is None:
        return None
    try:
        user_id = int(sub)
    except ValueError:
        return None
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if not user or not user.is_active:
            return None
        # detach; we only need scalar fields
        return user
    finally:
        db.close()


@router.websocket("/live")
async def ecg_live_ws(
    ws: WebSocket,
    token: str,
    analysis_id: Optional[int] = None,
    mode: str = "analysis",
    condition: Optional[str] = None,
    chunk_size: int = 24,
    tick_ms: int = 40,
    loop: bool = True,
):
    """
    Real-time ECG streaming over WebSocket.

    Query params:
    - token: JWT access token (required)
    - analysis_id: stream a stored upload (mode=analysis)
    - mode: analysis | synthetic_demo
    - condition: for synthetic_demo (e.g. N, A, V)
    - chunk_size, tick_ms, loop: pacing controls
    """
    user = _auth_user_from_token(token)
    if not user:
        await ws.close(code=4401)
        return

    await ws.accept()

    stored_path = None
    sampling_rate_hz = None
    if (mode or "").strip().lower() == "analysis":
        if not analysis_id:
            await ws.send_json({"type": "error", "message": "analysis_id is required for mode=analysis"})
            await ws.close(code=4400)
            return
        db = SessionLocal()
        try:
            a = db.get(ECGAnalysis, int(analysis_id))
            if not a or a.user_id != user.id:
                await ws.send_json({"type": "error", "message": "analysis not found"})
                await ws.close(code=4404)
                return
            u = db.get(ECGUpload, a.upload_id)
            if not u:
                await ws.send_json({"type": "error", "message": "upload missing"})
                await ws.close(code=4404)
                return
            stored_path = u.stored_path
            sampling_rate_hz = a.sampling_rate_hz
        finally:
            db.close()

    try:
        signal, meta = build_stream_source(
            stored_csv_path=stored_path,
            sampling_rate_hz=sampling_rate_hz,
            mode=mode,
            condition=condition,
        )
    except Exception as e:
        await ws.send_json({"type": "error", "message": str(e)})
        await ws.close(code=1011)
        return

    await ws.send_json(
        {
            "type": "meta",
            "sampling_rate_hz": meta.sampling_rate_hz,
            "source": meta.source,
            "signal_length": meta.signal_length,
            "chunk_size": int(chunk_size),
            "tick_ms": int(tick_ms),
            "loop": bool(loop),
        }
    )

    seq = 0
    try:
        async for chunk in stream_signal_chunks(signal, chunk_size=chunk_size, tick_ms=tick_ms, loop=loop):
            # Ensure chunk is non-empty numeric floats (and log for debugging)
            cleaned = []
            for v in chunk or []:
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                if fv == fv and fv not in (float("inf"), float("-inf")):
                    cleaned.append(fv)
            if not cleaned:
                continue

            print("Sending chunk:", len(cleaned))

            # Contract: each data message must be { "chunk": [float, ...] }
            # Keep seq for debugging/ordering.
            await ws.send_json({"seq": seq, "chunk": cleaned})
            seq += 1
            # allow cooperative cancellation / ping handling
            await asyncio.sleep(0)
    except WebSocketDisconnect:
        return


@ws_router.websocket("/ws/ecg-stream/{analysis_id}")
async def ecg_stream_ws_compat(ws: WebSocket, analysis_id: int, token: Optional[str] = None):
    """
    Compatibility WebSocket endpoint expected by the monitor frontend.

    Path (no /api prefix): /ws/ecg-stream/{analysis_id}
    Payload: { "chunk": [float, ...] }
    """
    # Accept first so clients can see early error messages.
    await ws.accept()
    print(f"WS connection established: analysis_id={analysis_id}")

    # Optional auth: if token is provided, enforce user ownership.
    user = None
    if token:
        user = _auth_user_from_token(token)
        if not user:
            await ws.send_json({"type": "error", "message": "unauthorized"})
            await ws.close(code=4401)
            return

    db = SessionLocal()
    try:
        a = db.get(ECGAnalysis, int(analysis_id))
        if not a:
            await ws.send_json({"type": "error", "message": "analysis not found"})
            await ws.close(code=4404)
            return
        if user and a.user_id != user.id:
            await ws.send_json({"type": "error", "message": "forbidden"})
            await ws.close(code=4403)
            return
        u = db.get(ECGUpload, a.upload_id)
        if not u:
            await ws.send_json({"type": "error", "message": "upload missing"})
            await ws.close(code=4404)
            return

        signal, _meta = build_stream_source(
            stored_csv_path=u.stored_path,
            sampling_rate_hz=a.sampling_rate_hz,
            mode="analysis",
            condition=None,
        )
    except Exception as e:
        await ws.send_json({"type": "error", "message": str(e)})
        await ws.close(code=1011)
        return
    finally:
        db.close()

    seq = 0
    try:
        async for chunk in stream_signal_chunks(signal, chunk_size=24, tick_ms=40, loop=True):
            cleaned = []
            for v in chunk or []:
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                if fv == fv and fv not in (float("inf"), float("-inf")):
                    cleaned.append(fv)
            if not cleaned:
                continue
            print("Sending chunk:", len(cleaned))
            await ws.send_json({"seq": seq, "chunk": cleaned})
            seq += 1
            await asyncio.sleep(0)
    except WebSocketDisconnect:
        print("WS disconnect")
        return
