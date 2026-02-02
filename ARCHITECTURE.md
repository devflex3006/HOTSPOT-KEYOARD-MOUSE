# System Architecture

## 1. High-Level Design

The **Hotspot Keyboard & Mouse** system consists of two main components:
1.  **Android Client (Sender):** Captures touch input, applies partial processing, and transmits data via UDP/TCP.
2.  **Linux Server (Receiver):** Receives packets, applies "Capacitor" smoothing, and injects input into the OS via `/dev/uinput`.

## 2. Network Protocol

The system uses a hybrid UDP/TCP approach for optimal performance.

### UDP (Port 55556) - Movement Data
Used for high-frequency cursor and scroll data where latency is critical and occasional packet loss is acceptable.
-   **Movement:** `MOVE <dx> <dy>` (e.g., `MOVE 5 -3`)
-   **Scroll:** `SCROLL <vertical> <horizontal>` (e.g., `SCROLL 1 0`)

### TCP (Port 55557) - Control & Auth
Used for reliable delivery of state changes and authentication.
-   **Auth:** `AUTH <6-digit-code>`
-   **Clicks:** `CLICK <button> <state>` (e.g., `CLICK LEFT DOWN`)
-   **Keys:** `KEY <state> <keycode>` (e.g., `KEY DOWN KEY_A`)

### UDP (Port 55555) - Discovery
-   **Broadcast:** Client sends `HOTSPOT_KBM_DISCOVERY`
-   **Response:** Server replies with `HOTSPOT_KBM_SERVER\n<Name>\n<IP>\n<Port>`

## 3. The "Capacitor" Smoothing Algorithm

### Concept
Standard remote mouse apps map 1 network packet to 1 mouse movement, causing "stutter" if the network jitters.
Our solution introduces a buffer (the "Capacitor") on the server.

### Implementation (`smoother.py`)
1.  **Input (Charge):** Network packets arrive at irregular intervals (e.g., 10ms, 15ms, 8ms gaps). Movement is added to a floating-point buffer.
2.  **Output (Discharge):** A dedicated thread runs at a fixed 60 FPS (16.6ms).
    -   It calculates a "discharge" amount based on the current buffer size.
    -   `move = buffer * discharge_rate` (Adaptive: 16% - 27%)
3.  **Continuation:** If input stops, the system continues movement for ~100ms using a decaying velocity vector. This simulates momentum.

### Benefits
-   **Visual Smoothness:** The cursor updates at a consistent monitor refresh rate regardless of network jitter.
-   **Precision:** Sub-pixel accumulation ensures slow movements are accurate.

## 4. Android Client Architecture

-   **Language:** Kotlin + Jetpack Compose
-   **Package:** `com.flex.hotspotkbm`
-   **Input Handling:**
    -   **Accumulator:** Touch events are batched at ~83Hz to prevent network flooding.
    -   **Sensitivity:** Applied at the client side (`raw_delta * sensitivity`).
    -   **Thresholds:** Scroll events must exceed `150f` pixels to trigger, preventing accidental scrolls.

## 5. Security

-   **Isolation:** Designed for local Hotspot networks (no internet required).
-   **Pairing:** 6-digit dynamic code generated at server startup.
-   **Single-Client:** Server accepts only one authenticated client at a time for exclusivity.
