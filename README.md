# HOTSPOT KEYBOARD & MOUSE
**Production Release v1.0.0**

A professional-grade remote input system that turns your Android device into a low-latency, high-precision trackpad and keyboard for Linux.

> **Designed by Flex** | Implemented with AI Assistance

---

## 🚀 Overview

This application allows you to control your Linux computer using your Android phone over a local Hotspot network. Unlike standard remote mouse apps, this project uses a unique **Capacitor-Style Smoothing Algorithm** designed to mimic the feel of high-end gaming mice.

**Key Features:**
- **Zero-Lag Input:** Uses UDP for high-performance cursor movement.
- **Gaming-Grade Smoothness:** Custom "Capacitor" algorithm eliminates jitter and gaps.
- **Dynamic Sensitivity:** Adjustable sensitivity multipliers (0.5x - 1.5x).
- **Two-Finger Scroll:** Smooth, momentum-based scrolling with threshold detection.
- **Secure Pairing:** 6-digit authentication code tied to the active session.
- **Production Ready:** Robust error handling, clean logging, and auto-reconnection.

---

## 💡 Key Concepts: The "Capacitor" Model

The core innovation in this project is the input smoothing logic, designed by **Flex**.

### 1. The Capacitor Analogy
Just as an electrical capacitor stores charge and releases it smoothly, our input smoother:
- **Charges:** Accumulates raw touch data from the Android device.
- **Discharges:** Releases movement at a constant 60 FPS (frames per second).
- **Result:** Even if network packets arrive irregularly (jitter), the cursor moves in a perfectly fluid line.

### 2. Gaming-Style Sensitivity
Sensitivity is handled using dynamic multipliers:
- **Accumulation:** Raw touch deltas are captured at roughly 83 FPS.
- **Scaling:** `output_pixels = raw_pixels * sensitivity_multiplier`
- **Sub-pixel Precision:** Fractional pixels are stored and carried over to the next frame, ensuring not a single micro-movement is lost.

---

## 🛠️ Installation & Usage

### 1. Prerequisites
- **Linux PC** (Root access required for `/dev/uinput`)
- **Python 3.8+**
- **Android Device** (Android 8.0+)

### 2. Linux Server Setup
```bash
# Nagivate to project directory
cd /home/flex/Projects/HOTSPOT_KEYBOARD_MOUSE

# Install dependencies (standard library only, but good to check)
pip install -r requirements.txt

# Run the server (Root required for virtual input creation)
sudo python3 -m server.main
```
*You will see a styled banner with your IP and a unique **Pairing Code**.*

### 3. Android Client Setup
1. Connect your Android phone to the **same Hotspot/Wi-Fi** as your PC.
2. Build and install the app (package: `com.flex.hotspotkbm`).
3. Open the app - it will auto-discover the server.
4. Enter the **Pairing Code** displayed on the server terminal.

---

## 🎮 Controls

### Trackpad Mode
- **1 Finger:** Move cursor (Smooth, accelerated)
- **2 Fingers:** Scroll (Vertical & Horizontal)
- **Tap:** Left Click
- **Double Tap:** Left Click

### Mouse Buttons
- **Left/Right Buttons:** Dedicated large buttons for ease of use.

### Keyboard
- **Toggle Icon:** Opens Android soft keyboard.
- **Typing:** Sends keys directly to Linux (supports shortcuts like Ctrl+C, Alt+Tab).

---

## 👨‍💻 Credits & Design

**Concept & Orchestration:** Flex  
**Architecture:** Capacitor-Style Input System  
**Implementation:** Developed with Advanced Agentic AI

This project realizes Flex's vision of a remote input device that doesn't *feel* remote. By prioritizing the "Capacitor" smoothing model over raw 1:1 input, we achieved a fluid experience comparable to hardware trackpads.

---

## ⚖️ License
Proprietary / Personal Use.
