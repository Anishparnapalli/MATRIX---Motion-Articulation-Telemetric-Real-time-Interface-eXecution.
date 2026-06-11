"""
bridge.py  —  M.A.T.R.I.X. Communication Bridge
═══════════════════════════════════════════════════════════════════════
Upgraded for full RTOS / NON-RTOS simulation protocol.

ARCHITECTURE
────────────
  Browser (WebSocket :8765)
       ↕
  bridge.py  ←— runs on Windows host
       ↕
  QNX Robotic_ARM  (TCP :12345)

WHAT THIS BRIDGE DOES
──────────────────────
  1. TCP server on port 12345  — QNX connects here
     • Receives CSV angle packets: "j0,j1,j2,j3,j4,j5\n"
     • Receives EMERGENCY_STOP
     • Receives WATCHDOG_HIT:<ms_over>
     • Receives POSE_DONE:<pose_idx>
     • Receives SEQ_COMPLETE

  2. WebSocket server on port 8765  — Browser connects here
     • Forwards all QNX packets → browser as JSON
     • Receives from browser:
         { type: "rtos_sequence", sequence: [[...],[...]], pose_duration_ms: 1000, total_poses: N }
         { type: "stop_cycle" }           — finish current pass then stop cycling
         { type: "emergency" }
         { type: "set_mode", mode: "rtos"|"nonrtos"|"manual" }
         { type: "send_sequence", sequence: [[...]] }   (legacy)

  3. Routes RTOS sequence from browser → QNX in a structured protocol:
       SEQ_START:<N_poses>:<duration_ms>\n
       POSE:<idx>:<j0>,<j1>,<j2>,<j3>,<j4>,<j5>\n
       ...
       SEQ_END\n

     QNX reads this, plans SCHED_FIFO execution, sends back POSE_DONE / SEQ_COMPLETE.

  4. Emergency from browser → QNX immediately: "EMERGENCY_STOP\n"

Run first:
  python bridge.py

Ports:
  12345  TCP   ← QNX connects here
  8765   WS    ← Browser connects here  ws://localhost:8765
"""

import asyncio
import socket
import threading
import json
import time
import queue
import websockets

# ────────────────────────────────────────────────────────────────────
#  Configuration
# ────────────────────────────────────────────────────────────────────
TCP_HOST = "0.0.0.0"
TCP_PORT = 12345
WS_HOST  = "localhost"
WS_PORT  = 8765

# ────────────────────────────────────────────────────────────────────
#  Shared state  (TCP thread ↔ WS coroutines)
# ────────────────────────────────────────────────────────────────────
state = {
    "angles":        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "emergency":     False,
    "qnx_connected": False,
    "packets":       0,
    "mode":          "manual",
    "pose_idx":      0,
}
state_lock = threading.Lock()

# Queue for commands to send TO QNX (written by WS coroutines, read by TCP thread)
to_qnx_queue = queue.Queue()

# All connected WebSocket clients
ws_clients     = set()
ws_clients_lock = threading.Lock()

# asyncio loop (set when WS server starts)
ws_loop = None

# ────────────────────────────────────────────────────────────────────
#  Broadcast helpers
# ────────────────────────────────────────────────────────────────────
async def _broadcast(message: str):
    with ws_clients_lock:
        targets = set(ws_clients)
    if not targets:
        return
    results = await asyncio.gather(
        *[ws.send(message) for ws in targets],
        return_exceptions=True
    )
    # Silently ignore send errors (client disconnected)


def broadcast_from_thread(message: str):
    """Thread-safe: schedule a broadcast on the WS event loop."""
    if ws_loop and not ws_loop.is_closed():
        asyncio.run_coroutine_threadsafe(_broadcast(message), ws_loop)


# ────────────────────────────────────────────────────────────────────
#  TCP Server  — runs in its own daemon thread
# ────────────────────────────────────────────────────────────────────
def tcp_server_thread():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((TCP_HOST, TCP_PORT))
    srv.listen(1)
    print(f"[TCP]  Listening on {TCP_HOST}:{TCP_PORT}  ← waiting for QNX")

    while True:
        conn, addr = srv.accept()
        conn.settimeout(0.05)   # Non-blocking-ish recv for interleaved send
        print(f"[TCP]  QNX connected from {addr}")

        with state_lock:
            state["qnx_connected"] = True
            state["emergency"]     = False

        broadcast_from_thread(json.dumps({
            "type":          "status",
            "qnx_connected": True,
            "addr":          f"{addr[0]}:{addr[1]}"
        }))

        buf = ""
        try:
            while True:
                # ── Drain outgoing queue (browser → QNX) ──────────────
                while not to_qnx_queue.empty():
                    try:
                        cmd = to_qnx_queue.get_nowait()
                        conn.sendall(cmd.encode("utf-8"))
                    except Exception as e:
                        print(f"[TCP]  Send error: {e}")

                # ── Receive from QNX ───────────────────────────────────
                try:
                    raw = conn.recv(4096).decode("utf-8", errors="ignore")
                except socket.timeout:
                    raw = ""
                except Exception:
                    break

                if raw == "":
                    # timeout, not disconnected — check queue again
                    time.sleep(0.005)
                    continue

                buf += raw

                # Process every complete line
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    _handle_qnx_line(line)

        except Exception as e:
            print(f"[TCP]  Connection error: {e}")
        finally:
            conn.close()
            with state_lock:
                state["qnx_connected"] = False
            print("[TCP]  QNX disconnected. Waiting for reconnect…")
            broadcast_from_thread(json.dumps({
                "type":          "status",
                "qnx_connected": False,
                "addr":          "—"
            }))


def _handle_qnx_line(line: str):
    """Parse one line received from QNX and broadcast to browser."""

    # ── EMERGENCY_STOP ───────────────────────────────────────────
    if line == "EMERGENCY_STOP":
        with state_lock:
            state["emergency"] = True
        print("[TCP]  ⚠ EMERGENCY_STOP received from QNX!")
        broadcast_from_thread(json.dumps({
            "type":   "emergency",
            "source": "qnx"
        }))
        return

    # ── WATCHDOG_HIT:<ms_over> ───────────────────────────────────
    if line.startswith("WATCHDOG_HIT:"):
        try:
            ms_over = float(line.split(":", 1)[1])
        except Exception:
            ms_over = 0.0
        print(f"[TCP]  ⏱ Watchdog: deadline missed by {ms_over:.1f}ms")
        broadcast_from_thread(json.dumps({
            "type":      "watchdog",
            "missed_ms": ms_over
        }))
        return

    # ── POSE_DONE:<pose_idx> ─────────────────────────────────────
    if line.startswith("POSE_DONE:"):
        try:
            idx = int(line.split(":", 1)[1])
        except Exception:
            idx = 0
        with state_lock:
            state["pose_idx"] = idx
        print(f"[TCP]  ✔ Pose #{idx+1} done")
        broadcast_from_thread(json.dumps({
            "type":     "pose_advance",
            "pose_idx": idx + 1
        }))
        return

    # ── CYCLE_DONE:<n> ────────────────────────────────────────────
    if line.startswith("CYCLE_DONE:"):
        try:
            cycle_num = int(line.split(":", 1)[1])
        except Exception:
            cycle_num = 0
        print(f"[TCP]  🔁 Cycle #{cycle_num} complete")
        broadcast_from_thread(json.dumps({
            "type":      "cycle_done",
            "cycle_num": cycle_num
        }))
        return

    # ── SEQ_COMPLETE ─────────────────────────────────────────────
    if line == "SEQ_COMPLETE":
        print("[TCP]  ✔ RTOS cycling stopped — SEQ_COMPLETE")
        broadcast_from_thread(json.dumps({"type": "seq_complete"}))
        return

    # ── ANGLES: "j0,j1,j2,j3,j4" or "j0,j1,j2,j3,j4,j5" ────────
    parts = line.split(",")
    if len(parts) in (5, 6):
        try:
            angles = [float(p) for p in parts]
            if len(angles) == 5:
                angles.append(0.0)   # gripper default

            with state_lock:
                state["angles"]  = angles
                state["emergency"] = False
                state["packets"] += 1
                pkt = state["packets"]
                pidx = state["pose_idx"]

            broadcast_from_thread(json.dumps({
                "type":     "angles",
                "angles":   angles,
                "packets":  pkt,
                "pose_idx": pidx
            }))
        except ValueError:
            print(f"[TCP]  Bad packet: {line}")


# ────────────────────────────────────────────────────────────────────
#  WebSocket Server  — async, main thread
# ────────────────────────────────────────────────────────────────────
async def ws_handler(websocket):
    with ws_clients_lock:
        ws_clients.add(websocket)
    client_addr = websocket.remote_address
    print(f"[WS]   Browser connected  {client_addr}  (total: {len(ws_clients)})")

    # Send current state immediately on connect
    with state_lock:
        current = dict(state)
    await websocket.send(json.dumps({
        "type":          "init",
        "angles":        current["angles"],
        "emergency":     current["emergency"],
        "qnx_connected": current["qnx_connected"],
        "packets":       current["packets"],
    }))

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type", "")

            # ── RTOS Sequence: browser → bridge → QNX ──────────────
            if msg_type == "rtos_sequence":
                seq     = data.get("sequence", [])
                dur_ms  = data.get("pose_duration_ms", 1000)
                n_poses = len(seq)
                if n_poses == 0:
                    continue

                print(f"[WS]   RTOS sequence: {n_poses} poses, {dur_ms}ms/pose → QNX")

                # Build the protocol block to send to QNX
                lines = []
                lines.append(f"SEQ_START:{n_poses}:{dur_ms}")
                for idx, pose in enumerate(seq):
                    csv = ",".join(f"{v:.2f}" for v in pose)
                    lines.append(f"POSE:{idx}:{csv}")
                lines.append("SEQ_END")
                block = "\n".join(lines) + "\n"

                to_qnx_queue.put(block)

                # Ack to browser
                await websocket.send(json.dumps({
                    "type": "seq_ack",
                    "msg":  f"RTOS sequence ({n_poses} poses @ {dur_ms}ms) sent to QNX"
                }))

            # ── Legacy sequence send ────────────────────────────────
            elif msg_type == "send_sequence":
                seq = data.get("sequence", [])
                n   = len(seq)
                if n == 0:
                    continue
                dur_ms = 1000
                lines  = [f"SEQ_START:{n}:{dur_ms}"]
                for idx, pose in enumerate(seq):
                    csv = ",".join(f"{v:.2f}" for v in pose)
                    lines.append(f"POSE:{idx}:{csv}")
                lines.append("SEQ_END")
                to_qnx_queue.put("\n".join(lines) + "\n")
                await websocket.send(json.dumps({
                    "type": "seq_ack",
                    "msg":  f"Sequence ({n} poses) queued for QNX"
                }))

            # ── Emergency from browser → QNX ───────────────────────
            elif msg_type == "emergency":
                with state_lock:
                    state["emergency"] = True
                to_qnx_queue.put("EMERGENCY_STOP\n")
                print("[WS]   ⚠ Emergency from browser → QNX")
                # Broadcast to all OTHER browser tabs
                await _broadcast(json.dumps({"type": "emergency", "source": "browser"}))

            # ── Stop cycling: finish current pass then halt ─────────
            # Only meaningful in RTOS mode; the C code ignores it otherwise.
            elif msg_type == "stop_cycle":
                to_qnx_queue.put("SEQ_STOP\n")
                print("[WS]   SEQ_STOP → QNX  (will stop after current pass)")
                await websocket.send(json.dumps({
                    "type": "stop_cycle_ack",
                    "msg":  "Stop requested — arm will finish current cycle then halt"
                }))

            # ── Mode change (informational) ─────────────────────────
            elif msg_type == "set_mode":
                mode = data.get("mode", "manual")
                with state_lock:
                    state["mode"] = mode
                print(f"[WS]   Mode → {mode.upper()}")

            else:
                print(f"[WS]   From browser: {data}")

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        with ws_clients_lock:
            ws_clients.discard(websocket)
        print(f"[WS]   Browser disconnected {client_addr}  (total: {len(ws_clients)})")


# ────────────────────────────────────────────────────────────────────
#  Main
# ────────────────────────────────────────────────────────────────────
async def main():
    global ws_loop
    ws_loop = asyncio.get_running_loop()

    t = threading.Thread(target=tcp_server_thread, daemon=True, name="TCP-Server")
    t.start()

    async with websockets.serve(ws_handler, WS_HOST, WS_PORT):
        print(f"[WS]   WebSocket server on ws://{WS_HOST}:{WS_PORT}")
        print()
        print("═" * 60)
        print("  M.A.T.R.I.X. Bridge  —  RUNNING")
        print()
        print("  1. Open dashboard.html with Live Server in VS Code")
        print("  2. Start QNX VM and run ./Robotic_ARM")
        print()
        print("  Ports:  TCP :12345  ← QNX")
        print("          WS  :8765   ← Browser")
        print("═" * 60)
        print()
        await asyncio.Future()   # run forever


if __name__ == "__main__":
    asyncio.run(main())