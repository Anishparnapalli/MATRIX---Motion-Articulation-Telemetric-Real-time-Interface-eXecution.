# M.A.T.R.I.X.
### Motion Articulation & Telemetric Real-time Interface eXecution

> A Model-in-the-Loop Cyber-Physical System demonstrating real-time RTOS robotic arm control using QNX 8.0, visualised through a live Three.js web dashboard.

![Platform](https://img.shields.io/badge/Platform-QNX%208.0-blue)
![Language](https://img.shields.io/badge/Language-C%20%7C%20Python%20%7C%20HTML%20%7C%20CSS%20%7C%20Java-green)
![License](https://img.shields.io/badge/License-QNX-lightgrey)

---

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Repository Structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
  - [Layer 1 — QNX RTOS Controller](#layer-1--qnx-rtos-controller)
  - [Layer 2 — Python Bridge Server](#layer-2--python-bridge-server)
  - [Layer 3 — Web Dashboard](#layer-3--web-dashboard)
- [Running the System](#running-the-system)
- [Usage Guide](#usage-guide)
  - [Manual Mode](#manual-mode)
  - [RTOS Mode](#rtos-mode)
  - [NON-RTOS Mode](#non-rtos-mode)
  - [Teach & Record](#teach--record)
  - [Emergency Stop](#emergency-stop)
- [Performance Results](#performance-results)
- [RTOS vs NON-RTOS Comparison](#rtos-vs-non-rtos-comparison)
- [Project Team](#project-team)
- [Acknowledgements](#acknowledgements)
- [References](#references)

---

## Overview

M.A.T.R.I.X. was built as part of the **RTOS Programming (21IPE314P)** course at **SRM Institute of Science & Technology**, Kattankulathur, during the academic year 2025–26.

The project tackles a common gap in embedded systems education: RTOS concepts like preemption, deterministic scheduling, deadline monitoring, and priority-based execution are typically taught through diagrams and theory. M.A.T.R.I.X. makes them **observable** — a student can watch a priority-25 Safety Task instantly freeze a priority-10 Motion Task on screen, measure the difference in emergency response time, and see the contrast between RTOS and NON-RTOS behaviour in real time.

The system runs entirely on a standard laptop. No physical robotic hardware is required.

---

## System Architecture

The system is split into three layers, each running on different hardware and communicating through well-defined interfaces:

```
┌─────────────────────────────────────────────────────────────────┐
│                  QNX 8.0 RTOS Layer (VMware VM)                 │
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────┐  │
│  │  Motion Task    │  │  Safety Task    │  │ Watchdog Task  │  │
│  │  Priority 10    │  │  Priority 25    │  │  Priority 15   │  │
│  │  100ms period   │  │  (Highest)      │  │  Deadline mon. │  │
│  │  Sine-wave traj.│  │  Emergency stop │  │  100ms timeout │  │
│  └────────┬────────┘  └────────┬────────┘  └────────────────┘  │
│           │ CSV packets        │ EMERGENCY_STOP                  │
│           └──────────┬─────────┘                                 │
│                TCP :12345                                         │
└──────────────────────┼──────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│              Python Bridge Layer (Windows Host)                  │
│                                                                  │
│   TCP Server :12345  ←→  bridge.py  ←→  WebSocket Server :8765 │
│   Parse CSV → JSON           ↕           Broadcast to browser   │
│   Queue sequences          Bidirectional  Forward to QNX        │
└──────────────────────┬──────────────────────────────────────────┘
                       │  WebSocket ws://localhost:8765
┌──────────────────────▼──────────────────────────────────────────┐
│             Web Dashboard Layer (Browser)                        │
│                                                                  │
│   Three.js 3D Viewport │ Control Panel │ Teach & Record System  │
│   5-DOF Arm Assembly   │ Joint Sliders │ Pose Capture & Replay  │
│   Real-time Animation  │ RTOS/NON-RTOS │ Emergency Controls     │
│   Gripper SVG Diagram  │ Live Telemetry│ OBJ Model Loader       │
└─────────────────────────────────────────────────────────────────┘
```

### Communication Protocol

| Layer | Protocol | Address | Direction |
|---|---|---|---|
| QNX → Bridge | TCP | `192.168.206.1:12345` | Outbound |
| Bridge → Browser | WebSocket | `ws://localhost:8765` | Outbound |
| Browser → Bridge → QNX | WebSocket + TCP | Both ports | Inbound |

---

## Features

### RTOS Brain (QNX 8.0)
- **Three POSIX threads** under `SCHED_FIFO` scheduling with distinct priorities
- **Motion Task (Priority 10):** Computes smooth sine-wave trajectories for all 5 joints; sends CSV angle packets every 100 ms via TCP
- **Safety Task (Priority 25):** Idles at zero CPU cost until triggered; immediately preempts the Motion Task and sends `EMERGENCY_STOP`
- **Watchdog Task (Priority 15):** Uses `pthread_cond_timedwait` to monitor the 100 ms deadline; logs every violation
- **Mutex-protected shared state** for safe inter-thread communication

### Python Bridge
- Dual-server architecture: raw TCP for QNX, async WebSocket for browser — running concurrently
- Parses incoming CSV packets, converts to JSON, broadcasts to all connected browser tabs within milliseconds
- Handles bidirectional communication: sequences recorded on the dashboard are queued and delivered to QNX over TCP

### Web Dashboard
- **Three.js 3D viewport** loading user-uploaded `.OBJ` / `.STL` model files
- **Pivot-entity hierarchy** for mechanically accurate 5-DOF arm assembly with correct joint chaining
- **Axis calibration screen:** four-point click to auto-calculate each joint's geometric rotation centre
- **Edit Mode:** drag-and-reposition parts using `TransformControls` with live position readout
- **Teach-and-Record System:** manually pose the arm, capture poses, replay sequences in browser or transmit to QNX for RTOS-controlled autonomous replay
- **RTOS vs NON-RTOS mode selectors** with visually distinct behaviour under each mode
- **Gripper panel** with mechanical SVG diagram synced to the gripper slider
- **Project Hub** with persistent storage via IndexedDB — multiple arm configurations saved locally
- **Live telemetry panel** with packet count, FPS, and latency readout

---

## Tech Stack

| Component | Tool / Version |
|---|---|
| RTOS Platform | QNX 8.0 (VMware VM) |
| RTOS IDE | QNX Momentics IDE (Eclipse-based) |
| C Compiler | `qcc` with `-lpthread -lsocket -lm` |
| VM Software | VMware Workstation |
| Python Runtime | Python 3.10+ |
| Python Library | `websockets` (pip) |
| Browser | Chrome / Edge (latest) |
| Web Server | VS Code Live Server |
| 3D Engine | Three.js r128 (CDN) |
| 3D Loaders | `OBJLoader`, `STLLoader` |
| 3D Controls | `OrbitControls`, `TransformControls` |
| Network | VMnet8 Host-Only (`192.168.206.1`) |
| 3D Models | SolidWorks → `.OBJ` / `.STL` |

---

## Repository Structure

```
MATRIX_RTOS/
├── QNX_RoboticARM/
│   └── src/
│       └── MATRIX_Robotic_ARM.c       # Main RTOS C program (3 threads, TCP client)
│
├── python_bridge/
│   └── bridge.py                      # Async TCP + WebSocket bridge server
│
├── dashboard/
│   └── MATRIX_QNX_dashboard.html      # Single-file web dashboard (Three.js + JS)
│
├── models/                            # Place your .OBJ / .STL arm part files here
│   ├── Base.obj
│   ├── Arm_01.obj
│   ├── Arm_02.obj
│   ├── Arm_03.obj
│   ├── Wrist.obj
│   ├── Gripper_base.obj
│   ├── Gripper_1.obj
│   ├── Gripper_2.obj
│   ├── gear1.obj
│   └── gear2.obj
│
└── README.md
```

---

## Prerequisites

### On the Windows Host
- VMware Workstation (with QNX 8.0 VM already installed and configured)
- Python 3.10 or later
- VS Code with the **Live Server** extension
- Chrome or Edge (latest)

### On the QNX VM
- QNX 8.0 with Momentics IDE
- VMnet8 host-only network adapter configured
- The VM's host gateway should be reachable at `192.168.206.1`

### Python Dependency
```bash
pip install websockets
```

---

## Installation & Setup

### Layer 1 — QNX RTOS Controller

1. Open **QNX Momentics IDE**.
2. Create a new **QNX C Project** named `MATRIX_Robotic_ARM`.
3. Copy `QNX_RoboticARM/src/MATRIX_Robotic_ARM.c` into the project `src/` folder.
4. In **Project Properties → QNX C/C++ Project → Linker**, add the following libraries:
   ```
   -lpthread  -lsocket  -lm
   ```
5. Verify the bridge IP in the source file matches your VMnet8 host gateway:
   ```c
   #define BRIDGE_IP   "192.168.206.1"
   #define BRIDGE_PORT 12345
   ```
6. Build the project (`Ctrl+B`). Confirm there are no errors.

### Layer 2 — Python Bridge Server

1. Clone or copy `python_bridge/bridge.py` onto your Windows host.
2. Install the dependency:
   ```bash
   pip install websockets
   ```
3. Verify the ports in `bridge.py` match what you configured in the QNX source:
   ```python
   TCP_HOST = "0.0.0.0"
   TCP_PORT = 12345       # QNX connects here
   WS_PORT  = 8765        # Browser connects here
   ```

### Layer 3 — Web Dashboard

1. Open the `dashboard/` folder in **VS Code**.
2. Place all your `.OBJ` or `.STL` arm part files in the `models/` directory (or upload them via the dashboard UI at runtime).
3. Install the **Live Server** extension if not already present.
4. Right-click `MATRIX_QNX_dashboard.html` → **Open with Live Server**.

---

## Running the System

Start the layers **in this order**:

**Step 1 — Start the Python bridge:**
```bash
cd python_bridge
python bridge.py
```
You should see:
```
[TCP]  Listening on 0.0.0.0:12345  ← waiting for QNX
[WS]   WebSocket server on ws://localhost:8765
```

**Step 2 — Open the dashboard in the browser:**

Right-click `MATRIX_QNX_dashboard.html` → Open with Live Server.
Navigate to your project hub, create or open a project, upload your model files, calibrate joint axes, and click **LAUNCH MATRIX**.

**Step 3 — Start the QNX controller:**

In Momentics IDE, run the compiled binary on the QNX VM. The console should print:
```
[MAIN]   Motion Task   launched  (priority 10)
[MOTION] Started  --  Priority 10, period 100 ms
[SAFETY] Started  --  Priority 20 (HIGHEST)
[SAFETY] >>> Press ENTER in this terminal for Emergency Stop <<<
[MAIN]   System ONLINE.
```

The bridge terminal will confirm:
```
[TCP]  QNX connected from ('192.168.206.163', XXXXX)
[WS]   Browser connected (total: 1)
```

The dashboard arm will begin animating in real time.

---

## Usage Guide

### Manual Mode
Use the **Joint Control sliders** on the left panel to manually position each of the 5 joints and the gripper. The arm updates in real time.

### RTOS Mode
1. Select **RTOS** in the Operating Mode panel.
2. Record poses using the Teach & Record system (see below).
3. Click **RUN** to send the sequence to QNX for deterministic RTOS-controlled replay.
4. All five joints move simultaneously. Timing is guaranteed by `SCHED_FIFO`.

### NON-RTOS Mode
1. Select **NON-RTOS** in the Operating Mode panel.
2. Record poses and click **RUN**.
3. Joint updates execute sequentially in JavaScript simulation with 1.3 s per pose.
4. Under the **ADD LOAD** button, simulated CPU stress makes jitter and lag clearly visible.

### Teach & Record
1. Use the sliders to pose the arm.
2. Click **RECORD** to capture the current pose.
3. Repeat to build a multi-pose sequence (visible as `#01`, `#02`, etc. in the list).
4. Click **RUN** to replay in browser (NON-RTOS) or transmit to QNX (RTOS).
5. Click **CLEAR ALL** to discard the recorded sequence.

### Emergency Stop
- **From the dashboard:** Click the **EMERGENCY** button in the Operating Mode panel.
- **From the QNX terminal:** Press `Enter` in the Momentics console at any time.

In **RTOS mode**, the Safety Task (Priority 25) immediately preempts the Motion Task. The arm on the dashboard freezes and turns red within a single network round-trip (~28 ms average).

In **NON-RTOS mode**, the stop command queues behind the current task. Expect 220–380 ms delay with the arm visibly continuing to move after the trigger.

---

## Performance Results

All measurements were taken during live demonstration runs with QNX in VMware, the bridge on the Windows host, and Chrome displaying the dashboard.

### End-to-End Latency

| Condition | Average Latency | Worst Case |
|---|---|---|
| Normal operation | 15–20 ms | — |
| High CPU load (stressed VM + multiple tabs) | — | ~35 ms |

No dropped or reordered packets were observed across any test run.

### Motion Task Timing

| Scenario | Result |
|---|---|
| Normal operation | Held 100 ms period consistently; Watchdog never fired |
| Deliberate CPU starvation | Watchdog caught every deadline violation and logged correctly |

### RTOS vs NON-RTOS Timing Stability

| Mode | Update Interval Variance |
|---|---|
| RTOS | ±2–3 ms around 100 ms target |
| NON-RTOS (under load) | 20–80 ms (visibly choppy) |

### Emergency Stop Response (15 trials each mode)

| Mode | Average Response | Maximum Seen | On-Screen Behaviour |
|---|---|---|---|
| RTOS | ~28 ms | Under 50 ms | Arm halted and turned red immediately |
| NON-RTOS | ~290 ms | Over 380 ms | Arm kept moving, stopped after a clear delay |

---

## RTOS vs NON-RTOS Comparison

| Feature | RTOS (QNX SCHED_FIFO) | NON-RTOS (Simulated) |
|---|---|---|
| Scheduling | Priority-based, strict preemption | Sequential — tasks run one after another |
| Task Execution | All 5 joints updated simultaneously | Joints updated one by one with visible lag |
| Latency | Not visible in any test run | Clearly visible, worsened under load |
| Emergency Stop | ~28 ms average, always under 50 ms | 220–380 ms depending on task state |
| Motion Quality | Smooth and continuous across all joints | Choppy and uneven, especially under load |
| Key Guarantee | **Consistency** — same behaviour regardless of load | None — response time varies with system state |

> The key insight is not that RTOS is faster on average — it is that RTOS is **consistent**. The Safety Task always preempted the Motion Task the moment it was triggered because `SCHED_FIFO` does not let a higher-priority thread wait.

---

## Project Team

| Name | Register Number | Role |
|---|---|---|
| Dass J | RA2311004010072 | QNX RTOS C Controller, Thread Architecture |
| R K Sri Vaksann | RA2311004010114 | Python Bridge Server, Communication Protocol |
| Parnapalli Anish | RA2311004010117 | Web Dashboard, Three.js Arm Assembly |

**Guide:** Dr. S. Dhanalakshmi, Professor, Department of Electronics & Communication Engineering, SRM Institute of Science & Technology.

**Academic Advisor:** Dr. M S Vasanthi, Associate Professor, Dept. of ECE.

**Course:** RTOS Programming (21IPE314P), Academic Year 2025–26 (EVEN), SRM Institute of Science & Technology, Kattankulathur – 603203.

---

## Acknowledgements

- QNX Software Systems for academic licensing of QNX 8.0 and Momentics IDE.
- The Three.js community for the r128 library and loaders.
- All referenced authors whose work informed the architecture of this system (see References below).

---

## References

1. S. Xu, H. Pan, J. Ren and J. Su, "Design of the Modbus Communication through Serial Port in QNX Operation System," *2008 ISECS International Colloquium on Computing, Communication, Control, and Management*, Guangzhou, China, 2008, pp. 434–438. doi: [10.1109/CCCM.2008.271](https://doi.org/10.1109/CCCM.2008.271)

2. J. Sayyad, A. Jatti, K. Attarde, R. B. T and S. Deokar, "Real-Time Operating System for Multitasking Control in the Robotics and Automation Industry," *2023 International Conference on Intelligent Data Communication Technologies and Internet of Things (IDCIoT)*, Bengaluru, India, 2023, pp. 880–887. doi: [10.1109/IDCIoT56793.2023.10053493](https://doi.org/10.1109/IDCIoT56793.2023.10053493)

3. J. Abijith Narayana et al., "Standalone Kinematic Evaluation of a 5-DoF Robotic Manipulator via MATLAB Simulation," *2025 IEEE North Karnataka Subsection Flagship International Conference (NKCon)*, Hubballi, India, 2025, pp. 1–6. doi: [10.1109/NKCon66957.2025.11345793](https://doi.org/10.1109/NKCon66957.2025.11345793)

4. P. P. Modi et al., "Interactive IIoT-Based 5DOF Robotic Arm for Upper Limb Telerehabilitation," *IEEE Access*, vol. 10, pp. 114919–114928, 2022. doi: [10.1109/ACCESS.2022.3218053](https://doi.org/10.1109/ACCESS.2022.3218053)

5. J.-H. Kim, J.-H. Choi, Y.-C. An and T.-Y. Kuc, "Evaluation of RTOS for Robotic Applications with ROS2 on Embedded Systems," *2025 25th International Conference on Control, Automation and Systems (ICCAS)*, Incheon, Korea, 2025, pp. 560–565. doi: [10.23919/ICCAS66577.2025.11301358](https://doi.org/10.23919/ICCAS66577.2025.11301358)

6. T. Cernat, M. Daraban, C. Corches and G. Chindris, "Preemptive Real Time Operating System for Low Power Microcontrollers," *2023 IEEE 29th International Symposium for Design and Technology in Electronic Packaging (SIITME)*, Craiova, Romania, 2023, pp. 281–284. doi: [10.1109/SIITME59799.2023.10431365](https://doi.org/10.1109/SIITME59799.2023.10431365)

7. T. Huang et al., "P2TS: A Preemptive Approach for Priority-Aware Task Scheduling in Computing Power Networks," *IEEE Transactions on Mobile Computing*, vol. 25, no. 2, pp. 1840–1856, Feb. 2026. doi: [10.1109/TMC.2025.3606454](https://doi.org/10.1109/TMC.2025.3606454)

8. V. Mankani, C. Wadhwani and A. Deshpande, "Memory-Driven Robotic Arm with WiFi Enabled Control," *2024 Asia Pacific Conference on Innovation in Technology (APCIT)*, MYSORE, India, 2024, pp. 1–4. doi: [10.1109/APCIT62007.2024.10673477](https://doi.org/10.1109/APCIT62007.2024.10673477)

---

*SRM Institute of Science & Technology, Kattankulathur – 603203, Chengalpattu District | May 2026*
