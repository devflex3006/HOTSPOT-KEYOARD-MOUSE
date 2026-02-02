"""
uinput device wrappers for virtual mouse and keyboard input injection.

Requires root privileges to access /dev/uinput.
"""

import os
import struct
import fcntl
import ctypes
from typing import Optional

from .config import (
    MOUSE_DEVICE_NAME, KEYBOARD_DEVICE_NAME,
    KEY_MAP, BUTTON_MAP,
    EV_SYN, EV_KEY, EV_REL,
    REL_X, REL_Y, REL_WHEEL, REL_HWHEEL,
    SYN_REPORT
)


# ioctl constants
UINPUT_MAX_NAME_SIZE = 80

# ioctl request codes
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_SET_RELBIT = 0x40045566
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502

# uinput_user_dev structure
# struct uinput_user_dev {
#     char name[UINPUT_MAX_NAME_SIZE];
#     struct input_id id;
#         __u16 bustype;
#         __u16 vendor;
#         __u16 product;
#         __u16 version;
#     __s32 ff_effects_max;
#     __s32 absmax[ABS_CNT];  # 64 elements
#     __s32 absmin[ABS_CNT];
#     __s32 absfuzz[ABS_CNT];
#     __s32 absflat[ABS_CNT];
# };

# For simplicity, we'll use struct packing
# name: 80 bytes
# bustype, vendor, product, version: 4 * 2 bytes = 8 bytes
# ff_effects_max: 4 bytes
# abs arrays: 4 * 64 * 4 = 1024 bytes (we don't use these for rel devices)

UINPUT_USER_DEV_SIZE = 80 + 8 + 4 + (4 * 64 * 4)


class UInputDevice:
    """Base class for uinput virtual devices."""
    
    def __init__(self, name: str):
        self.name = name
        self.fd: Optional[int] = None
        self._closed = False
    
    def _open_uinput(self) -> int:
        """Open /dev/uinput and return file descriptor."""
        paths = ["/dev/uinput", "/dev/input/uinput"]
        for path in paths:
            if os.path.exists(path):
                try:
                    return os.open(path, os.O_WRONLY | os.O_NONBLOCK)
                except OSError:
                    continue
        raise OSError("Cannot open uinput device. Are you running as root?")
    
    def _write_event(self, ev_type: int, code: int, value: int):
        """Write an input event to the device."""
        if self.fd is None:
            raise RuntimeError("Device not initialized")
        
        # struct input_event {
        #     struct timeval time;  # 16 bytes on 64-bit
        #     __u16 type;
        #     __u16 code;
        #     __s32 value;
        # };
        # Total: 24 bytes on 64-bit systems
        
        # We use 0 for time (kernel will fill it in)
        event = struct.pack("llHHi", 0, 0, ev_type, code, value)
        os.write(self.fd, event)
    
    def _sync(self):
        """Send a sync event to flush the event queue."""
        self._write_event(EV_SYN, SYN_REPORT, 0)
    
    def _create_device(self, setup_func):
        """Create the uinput device with given setup function."""
        self.fd = self._open_uinput()
        
        # Setup event types and codes
        setup_func()
        
        # Write device info
        name_bytes = self.name.encode('utf-8')[:UINPUT_MAX_NAME_SIZE-1]
        name_bytes = name_bytes.ljust(UINPUT_MAX_NAME_SIZE, b'\x00')
        
        # Create uinput_user_dev structure
        user_dev = name_bytes
        # input_id: bustype=0x03 (BUS_USB), vendor=0x1234, product=0x5678, version=1
        user_dev += struct.pack("HHHH", 0x03, 0x1234, 0x5678, 1)
        # ff_effects_max
        user_dev += struct.pack("i", 0)
        # abs arrays (not used for relative devices)
        user_dev += b'\x00' * (4 * 64 * 4)
        
        os.write(self.fd, user_dev)
        
        # Create the device
        fcntl.ioctl(self.fd, UI_DEV_CREATE)
    
    def close(self):
        """Destroy the uinput device."""
        if self.fd is not None and not self._closed:
            try:
                fcntl.ioctl(self.fd, UI_DEV_DESTROY)
            except:
                pass
            try:
                os.close(self.fd)
            except:
                pass
            self._closed = True
            self.fd = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


class VirtualMouse(UInputDevice):
    """Virtual mouse device for cursor movement, scrolling, and clicks."""
    
    def __init__(self, name: str = MOUSE_DEVICE_NAME):
        super().__init__(name)
        self._setup_mouse()
    
    def _setup_mouse(self):
        """Configure and create the virtual mouse device."""
        def setup():
            # Enable event types
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)  # For buttons
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_REL)  # For movement
            
            # Enable mouse buttons
            for button_code in BUTTON_MAP.values():
                fcntl.ioctl(self.fd, UI_SET_KEYBIT, button_code)
            
            # Enable relative axes
            fcntl.ioctl(self.fd, UI_SET_RELBIT, REL_X)
            fcntl.ioctl(self.fd, UI_SET_RELBIT, REL_Y)
            fcntl.ioctl(self.fd, UI_SET_RELBIT, REL_WHEEL)
            fcntl.ioctl(self.fd, UI_SET_RELBIT, REL_HWHEEL)
        
        self._create_device(setup)
    
    def move(self, dx: int, dy: int):
        """Move the cursor by relative delta values."""
        if dx != 0:
            self._write_event(EV_REL, REL_X, dx)
        if dy != 0:
            self._write_event(EV_REL, REL_Y, dy)
        if dx != 0 or dy != 0:
            self._sync()
    
    def scroll(self, vertical: int, horizontal: int = 0):
        """
        Scroll the mouse wheel.
        
        Args:
            vertical: Positive = scroll up, Negative = scroll down
            horizontal: Positive = scroll right, Negative = scroll left
        """
        if vertical != 0:
            self._write_event(EV_REL, REL_WHEEL, vertical)
        if horizontal != 0:
            self._write_event(EV_REL, REL_HWHEEL, horizontal)
        if vertical != 0 or horizontal != 0:
            self._sync()
    
    def click(self, button: str, state: str):
        """
        Press or release a mouse button.
        
        Args:
            button: "LEFT", "RIGHT", or "MIDDLE"
            state: "DOWN" (press) or "UP" (release)
        """
        button_code = BUTTON_MAP.get(button.upper())
        if button_code is None:
            raise ValueError(f"Unknown button: {button}")
        
        value = 1 if state.upper() == "DOWN" else 0
        self._write_event(EV_KEY, button_code, value)
        self._sync()


class VirtualKeyboard(UInputDevice):
    """Virtual keyboard device for key press/release events."""
    
    def __init__(self, name: str = KEYBOARD_DEVICE_NAME):
        super().__init__(name)
        self._setup_keyboard()
    
    def _setup_keyboard(self):
        """Configure and create the virtual keyboard device."""
        def setup():
            # Enable key events
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
            
            # Enable all keys from our key map
            for keycode in KEY_MAP.values():
                fcntl.ioctl(self.fd, UI_SET_KEYBIT, keycode)
        
        self._create_device(setup)
    
    def key_event(self, key: str, state: str):
        """
        Press or release a key.
        
        Args:
            key: Key name (e.g., "KEY_A", "KEY_ENTER")
            state: "DOWN" (press) or "UP" (release)
        """
        keycode = KEY_MAP.get(key.upper())
        if keycode is None:
            raise ValueError(f"Unknown key: {key}")
        
        value = 1 if state.upper() == "DOWN" else 0
        self._write_event(EV_KEY, keycode, value)
        self._sync()
    
    def type_key(self, key: str):
        """Press and release a key (convenience method)."""
        self.key_event(key, "DOWN")
        self.key_event(key, "UP")
