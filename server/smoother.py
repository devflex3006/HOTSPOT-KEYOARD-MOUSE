"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              CAPACITOR-STYLE INPUT SMOOTHER                                  ║
║                                                                              ║
║  Created by: Flex                                                            ║
║  Concept: Gaming-style sensitivity with capacitor discharge smoothing        ║
╚══════════════════════════════════════════════════════════════════════════════╝

THE CAPACITOR ANALOGY
=====================
Imagine a capacitor in an electronic circuit:
- Input: Irregular packets with varying gaps (network jitter)
- Capacitor: Stores "charge" (accumulated movement)
- Output: Constant, smooth current (steady mouse movement)

Just like a capacitor smooths electrical current in a circuit, this smoother
buffers incoming mouse movement and releases it at a steady rate, eliminating
gaps and jitter in the output.

HOW IT WORKS
============
1. CHARGE PHASE (add_movement):
   - Incoming movement packets "charge" the capacitor buffer
   - Velocity is tracked for continuation after input stops
   - Direction is stored for momentum-based continuation

2. DISCHARGE PHASE (_discharge_loop):
   - Runs at fixed FPS (e.g., 60 Hz) - gaming standard
   - Each frame, a percentage of stored charge is released
   - Sub-pixel accumulation ensures no movement is lost
   - Adaptive discharge: faster for large movements, slower for small

3. CONTINUATION PHASE:
   - When input stops, movement continues briefly (momentum)
   - Smooth ease-out curve mimics natural deceleration
   - Prevents jarring stops during slow movements

SENSITIVITY MULTIPLIERS (Gaming-Style)
======================================
- Discharge Rate: How much of the buffer to output per frame (0.14-0.18)
- Continuation Timeout: How long to continue after input stops (80-120ms)
- Smoothing Factor: Blend between raw and smoothed velocity (0.3-0.4)
- Velocity Decay: How quickly momentum fades (0.6-0.7)

These parameters are tuned for gaming-style responsiveness while maintaining
smoothness - the hallmark of professional gaming mice and trackpads.
"""

import threading
import time
from collections import deque
from typing import Callable, Optional
import math


class InputSmoother:
    """
    Capacitor-style movement buffer for ultra-smooth cursor movement.
    
    This class implements the "capacitor" smoothing algorithm:
    - Accumulates movement like a capacitor charges
    - Discharges at a constant rate for smooth, gap-free output
    - Provides momentum-based continuation after input stops
    
    Key Parameters:
        discharge_rate: Percentage of buffer released per frame (0.0-1.0)
                       Higher = more responsive, Lower = smoother
        continuation_timeout_ms: Duration to continue movement after input stops
                                Higher = more momentum, Lower = tighter control
        smoothing_factor: Blend factor for velocity averaging
        velocity_decay: How quickly momentum fades during continuation
    
    Example:
        smoother = InputSmoother(
            inject_move=mouse.move,
            target_fps=60,
            discharge_rate=0.18,  # Release 18% per frame
            continuation_timeout_ms=120
        )
        smoother.start()
        smoother.add_movement(dx, dy)  # Call with each input packet
    """
    
    def __init__(
        self,
        inject_move: Callable[[int, int], None],
        target_fps: int = 60,
        discharge_rate: float = 0.22,  # Optimization R3: 22% discharge (faster response)
        continuation_timeout_ms: int = 80,  # Optimization R3: 80ms (tighter control)
        smoothing_factor: float = 0.35,
        velocity_decay: float = 0.75  # Optimization R3: 75% decay (smoother tail)
    ):
        """
        Initialize the capacitor-style input smoother.
        
        Args:
            inject_move: Callback to inject movement into the system (dx, dy)
            target_fps: Output frame rate (60 = standard, 120 = high-refresh)
            discharge_rate: Fraction of buffer to release per frame (0.0-1.0)
                           0.14 = very smooth, 0.22 = very responsive
            continuation_timeout_ms: How long to continue after input stops (ms)
                                    Lower (80) = tighter, Higher (120) = more momentum
            smoothing_factor: Velocity averaging blend (0.0-1.0)
            velocity_decay: Momentum fade rate during continuation (0.0-1.0)
        """
        # === OUTPUT CALLBACK ===
        self._inject_move = inject_move
        
        # === TIMING CONFIGURATION ===
        self._target_fps = target_fps  # Frames per second for output
        self._discharge_rate = discharge_rate  # Base discharge rate
        self._continuation_timeout = continuation_timeout_ms / 1000.0  # Convert to seconds
        self._smoothing_factor = smoothing_factor
        self._velocity_decay = velocity_decay
        
        # === THE CAPACITOR (Movement Buffer) ===
        # Stores accumulated movement like charge in a capacitor
        # Positive X = right, Negative X = left
        # Positive Y = down, Negative Y = up
        self._charge_x = 0.0
        self._charge_y = 0.0
        
        # === SUB-PIXEL ACCUMULATOR ===
        # Stores fractional pixels to ensure no movement is lost
        # Essential for slow, precise movements
        self._subpixel_x = 0.0
        self._subpixel_y = 0.0
        
        # === VELOCITY TRACKING (for continuation) ===
        # Smoothed velocity used for momentum after input stops
        self._velocity_x = 0.0
        self._velocity_y = 0.0
        
        # === DIRECTION VECTOR (for continuation) ===
        # Unit vector of movement direction
        self._direction_x = 0.0
        self._direction_y = 0.0
        self._speed = 0.0  # Magnitude of velocity
        
        # === TIMING STATE ===
        self._last_input_time = 0.0  # When we last received input
        self._is_active = False  # Whether we're currently processing movement
        
        # === THREAD CONTROL ===
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()  # Protects all state variables
    
    def start(self):
        """
        Start the discharge loop thread.
        
        This begins the constant-rate output that runs at target_fps,
        providing smooth movement regardless of input packet timing.
        """
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._discharge_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop the discharge loop and cleanup."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.5)
            self._thread = None
    
    def add_movement(self, dx: int, dy: int):
        """
        CHARGE the capacitor with incoming movement.
        
        This is called for each incoming movement packet from the network.
        Movement is stored in the buffer and will be discharged smoothly.
        
        Args:
            dx: Horizontal movement (positive = right)
            dy: Vertical movement (positive = down)
        
        The capacitor model:
        - Movement adds to the existing charge
        - Velocity is calculated for continuation
        - Direction is stored for momentum
        """
        current_time = time.time()
        
        with self._lock:
            # === ADD TO CAPACITOR CHARGE ===
            # Incoming movement adds to the buffer
            self._charge_x += dx
            self._charge_y += dy
            
            # === CALCULATE VELOCITY FOR CONTINUATION ===
            # This allows momentum to continue after input stops
            interval = 1.0 / self._target_fps
            dt = current_time - self._last_input_time if self._last_input_time > 0 else interval
            if dt < 0.001:
                dt = interval  # Prevent division issues
            
            # Calculate frames elapsed since last input
            frames = max(dt * self._target_fps, 1)
            
            # Calculate velocity as movement per frame
            new_vx = dx / frames
            new_vy = dy / frames
            
            # === QUICK TURN LOGIC (Optimization) ===
            # If new movement opposes current velocity, reset momentum immediately
            # This prevents the "drifty" feeling when changing direction quickly
            # Dot product < 0 means opposing directions
            if (dx * self._velocity_x + dy * self._velocity_y) < 0:
                self._velocity_x = 0
                self._velocity_y = 0
            
            # === SMOOTH VELOCITY (exponential moving average) ===
            # Blend new velocity with previous for stability
            # Optimization R3: 0.6 (60% new) makes it react faster to input changes
            blend = 0.6
            self._velocity_x = self._velocity_x * (1 - blend) + new_vx * blend
            self._velocity_y = self._velocity_y * (1 - blend) + new_vy * blend
            
            # === UPDATE DIRECTION VECTOR ===
            # Store normalized direction for continuation
            speed = math.sqrt(self._velocity_x**2 + self._velocity_y**2)
            if speed > 0.05:  # Minimum threshold to update direction
                self._direction_x = self._velocity_x / speed
                self._direction_y = self._velocity_y / speed
                self._speed = speed
            
            # === UPDATE STATE ===
            self._is_active = True
            self._last_input_time = current_time
    
    def _discharge_loop(self):
        """
        DISCHARGE the capacitor at a constant rate.
        
        This is the heart of the smoothing algorithm. It runs at a fixed
        frame rate (target_fps) and outputs movement continuously.
        
        The loop handles three states:
        1. DISCHARGE: Buffer has charge → output portion of it
        2. CONTINUATION: Buffer empty but within timeout → add momentum
        3. IDLE: Timeout reached → stop movement
        
        This provides smooth, gap-free cursor movement regardless of
        when input packets arrive.
        """
        interval = 1.0 / self._target_fps  # Time between frames
        
        while self._running:
            loop_start = time.time()
            
            with self._lock:
                current_time = time.time()
                time_since_input = current_time - self._last_input_time
                
                out_dx = 0.0
                out_dy = 0.0
                
                # === STATE 1: DISCHARGE (buffer has charge) ===
                if self._charge_x != 0 or self._charge_y != 0:
                    # Calculate charge magnitude for adaptive discharge
                    charge_magnitude = math.sqrt(self._charge_x**2 + self._charge_y**2)
                    
                    # === ADAPTIVE DISCHARGE RATE ===
                    # Like an RC circuit: more charge = faster discharge
                    # This provides:
                    # - Fast response for large movements (gaming)
                    # - Smooth precision for small movements (accuracy)
                    if charge_magnitude > 10:
                        # Large movement: discharge faster (up to 27%)
                        rate = min(self._discharge_rate * 1.5, 0.27)
                    elif charge_magnitude < 2:
                        # Small movement: discharge slower (minimum 12%)
                        rate = max(self._discharge_rate * 0.7, 0.12)
                    else:
                        # Normal movement: use base rate
                        rate = self._discharge_rate
                    
                    # === CALCULATE DISCHARGE AMOUNT ===
                    out_dx = self._charge_x * rate
                    out_dy = self._charge_y * rate
                    
                    # === REMOVE DISCHARGED AMOUNT FROM BUFFER ===
                    self._charge_x -= out_dx
                    self._charge_y -= out_dy
                    
                    # === CLEAR TINY RESIDUALS ===
                    # When charge is nearly zero, release everything
                    # Prevents "stuck" sub-pixel amounts
                    if abs(self._charge_x) < 0.02:
                        out_dx += self._charge_x
                        self._charge_x = 0
                    if abs(self._charge_y) < 0.02:
                        out_dy += self._charge_y
                        self._charge_y = 0
                
                # === STATE 2: CONTINUATION (momentum after input stops) ===
                elif self._is_active and time_since_input < self._continuation_timeout:
                    # Calculate progress through continuation (0.0 → 1.0)
                    progress = time_since_input / self._continuation_timeout
                    
                    # === SMOOTH EASE-OUT CURVE ===
                    # Like a capacitor discharge curve: fast at first, then slows
                    # pow(1-progress, 2) gives quadratic ease-out
                    fade = math.pow(1.0 - progress, 2)
                    
                    # Calculate continuation speed with fade
                    continue_speed = self._speed * fade * 0.5
                    
                    # Add continuation movement in stored direction
                    if continue_speed > 0.03:  # Minimum threshold
                        out_dx = self._direction_x * continue_speed
                        out_dy = self._direction_y * continue_speed
                
                # === STATE 3: IDLE (timeout reached) ===
                elif self._is_active and time_since_input >= self._continuation_timeout:
                    # Reset state - no more movement
                    self._is_active = False
                    self._speed = 0
                    self._velocity_x = 0
                    self._velocity_y = 0
                
                # === SUB-PIXEL ACCUMULATION ===
                # Accumulate fractional pixels to ensure precision
                # This is critical for slow, accurate movements
                self._subpixel_x += out_dx
                self._subpixel_y += out_dy
                
                # Extract integer pixels for output
                int_dx = int(self._subpixel_x)
                int_dy = int(self._subpixel_y)
                
                # Keep the fractional part for next frame
                self._subpixel_x -= int_dx
                self._subpixel_y -= int_dy
                
                # === OUTPUT TO SYSTEM ===
                # Inject movement into the virtual mouse
                if int_dx != 0 or int_dy != 0:
                    self._inject_move(int_dx, int_dy)
            
            # === MAINTAIN CONSTANT FRAME RATE ===
            # Sleep for remaining time in this frame
            elapsed = time.time() - loop_start
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)


class ScrollSmoother:
    """
    Scroll smoother with momentum.
    
    Provides smooth scrolling with momentum/inertia effect.
    When the user stops scrolling, movement continues briefly
    and gradually slows down.
    
    Parameters:
        momentum_decay: How quickly scroll momentum fades (0.0-1.0)
                       Higher = longer scroll coast, Lower = quicker stop
    """
    
    def __init__(self, inject_scroll: Callable[[int, int], None], momentum_decay: float = 0.85):
        """
        Initialize scroll smoother.
        
        Args:
            inject_scroll: Callback to inject scroll events (vertical, horizontal)
            momentum_decay: Momentum fade rate per frame (0.0-1.0)
        """
        self._inject_scroll = inject_scroll
        self._momentum_decay = momentum_decay
        
        # Momentum accumulators
        self._momentum_v = 0.0  # Vertical scroll momentum
        self._momentum_h = 0.0  # Horizontal scroll momentum
        
        # Thread control
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
    
    def start(self):
        """Start the scroll momentum loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop the scroll momentum loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.5)
    
    def add_scroll(self, vertical: int, horizontal: int = 0):
        """
        Add scroll input with momentum.
        
        Args:
            vertical: Vertical scroll amount (positive = up)
            horizontal: Horizontal scroll amount (positive = right)
        """
        with self._lock:
            # Add to momentum with scaling factor
            self._momentum_v += vertical * 0.5
            self._momentum_h += horizontal * 0.5
    
    def _loop(self):
        """Main scroll momentum loop."""
        while self._running:
            with self._lock:
                # Process vertical scroll momentum
                if abs(self._momentum_v) >= 0.5:
                    v = 1 if self._momentum_v > 0 else -1
                    self._inject_scroll(v, 0)
                    self._momentum_v *= self._momentum_decay
                    if abs(self._momentum_v) < 0.5:
                        self._momentum_v = 0
                
                # Process horizontal scroll momentum
                if abs(self._momentum_h) >= 0.5:
                    h = 1 if self._momentum_h > 0 else -1
                    self._inject_scroll(0, h)
                    self._momentum_h *= self._momentum_decay
                    if abs(self._momentum_h) < 0.5:
                        self._momentum_h = 0
            
            time.sleep(0.016)  # ~60 FPS
