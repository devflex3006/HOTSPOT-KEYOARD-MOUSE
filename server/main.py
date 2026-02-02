#!/usr/bin/env python3
"""
HOTSPOT KEYBOARD & MOUSE - Linux Server

Main entry point that orchestrates all server components.
Requires root privileges to access uinput.
"""

import os
import sys
import signal
import socket
import logging
import argparse
from typing import Optional

from .uinput_device import VirtualMouse, VirtualKeyboard
from .auth import AuthManager
from .connection import ConnectionManager
from .discovery import DiscoveryService
from .network import UDPInputListener, TCPControlListener
from .smoother import InputSmoother, ScrollSmoother
from .config import DISCOVERY_PORT, INPUT_PORT, CONTROL_PORT

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_local_ip() -> str:
    """Get the local IP address (preferring hotspot/wlan interface)."""
    try:
        # Try to get the IP by creating a dummy connection
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        pass
    
    # Fallback to localhost
    return "127.0.0.1"


def check_privileges():
    """Check if running with root privileges."""
    if os.geteuid() != 0:
        print("=" * 50)
        print("ERROR: This server requires root privileges")
        print("       to access /dev/uinput")
        print()
        print("Run with: sudo python3 -m server.main")
        print("=" * 50)
        sys.exit(1)


def print_banner(ip: str, pairing_code: str):
    """
    Print the server startup banner with styled formatting.
    
    Uses box-drawing characters and ANSI colors for a professional,
    visually appealing terminal display.
    """
    # === ANSI Color Codes ===
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    MAGENTA = "\033[95m"
    WHITE = "\033[97m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"
    
    width = 62
    
    print()
    print(f"{CYAN}╔{'═' * width}╗{RESET}")
    print(f"{CYAN}║{BOLD}{WHITE}{'HOTSPOT KEYBOARD & MOUSE SERVER':^{width}}{RESET}{CYAN}║{RESET}")
    print(f"{CYAN}║{DIM}{'v1.0.0 (Production) - Created by Flex':^{width}}{RESET}{CYAN}║{RESET}")
    print(f"{CYAN}╠{'═' * width}╣{RESET}")
    print(f"{CYAN}║{RESET}  {WHITE}IP Address:{RESET}    {GREEN}{ip:<44}{RESET} {CYAN}║{RESET}")
    print(f"{CYAN}║{RESET}  {WHITE}Discovery:{RESET}     {DIM}UDP {DISCOVERY_PORT:<40}{RESET} {CYAN}║{RESET}")
    print(f"{CYAN}║{RESET}  {WHITE}Input (UDP):{RESET}   {DIM}{INPUT_PORT:<44}{RESET} {CYAN}║{RESET}")
    print(f"{CYAN}║{RESET}  {WHITE}Control (TCP):{RESET} {DIM}{CONTROL_PORT:<44}{RESET} {CYAN}║{RESET}")
    print(f"{CYAN}╠{'═' * width}╣{RESET}")
    print(f"{CYAN}║{RESET}  {YELLOW}🔑 PAIRING CODE:{RESET}  {BOLD}{MAGENTA}{pairing_code}{RESET}                                    {CYAN}║{RESET}")
    print(f"{CYAN}╚{'═' * width}╝{RESET}")
    print()
    log_status("Server started successfully. Waiting for App connection...")


def log_status(message: str, icon: str = "⏳"):
    """Log a status message with timestamp and icon."""
    from datetime import datetime
    timestamp = datetime.now().strftime("%H:%M:%S")
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    DIM = "\033[2m"
    RESET = "\033[0m"
    print(f"{DIM}[{timestamp}]{RESET} {icon} {WHITE}{message}{RESET}")


def log_event(event_type: str, message: str):
    """Log an event with appropriate styling based on type."""
    from datetime import datetime
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    # Color map for different event types
    colors = {
        "success": ("\033[92m", "✓"),   # Green
        "warning": ("\033[93m", "⚠"),   # Yellow
        "error": ("\033[91m", "✗"),     # Red
        "info": ("\033[96m", "ℹ"),      # Cyan
        "connect": ("\033[92m", "🔗"),  # Green
        "disconnect": ("\033[93m", "🔄"),  # Yellow
        "auth": ("\033[95m", "🔑"),     # Magenta
    }
    
    color, icon = colors.get(event_type, ("\033[97m", "•"))
    DIM = "\033[2m"
    RESET = "\033[0m"
    
    print(f"{DIM}[{timestamp}]{RESET} {icon} {color}{message}{RESET}")


def log_pairing_code(code: str):
    """Display new pairing code with styled formatting."""
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"
    RESET = "\033[0m"
    log_event("auth", f"New Pairing Code: {BOLD}{MAGENTA}{code}{RESET}")


class HotspotKBMServer:
    """Main server class that orchestrates all components."""
    
    def __init__(self):
        self.mouse: Optional[VirtualMouse] = None
        self.keyboard: Optional[VirtualKeyboard] = None
        self.auth_manager = AuthManager()
        self.connection_manager = ConnectionManager()
        self.discovery_service: Optional[DiscoveryService] = None
        self.udp_listener: Optional[UDPInputListener] = None
        self.tcp_listener: Optional[TCPControlListener] = None
        self.input_smoother: Optional[InputSmoother] = None
        self.scroll_smoother: Optional[ScrollSmoother] = None
        self._running = False
        self._local_ip = ""
    
    def _on_auth(self, client_socket: socket.socket, client_ip: str, code: str):
        """Handle authentication attempt."""
        expected_code = self.auth_manager.current_code
        logger.debug(f"Auth attempt from {client_ip}: received='{code}' expected='{expected_code}'")
        
        if self.auth_manager.validate_code(code):
            # Check if we can accept this client
            if self.connection_manager.try_connect(client_ip, client_socket):
                self.tcp_listener.set_authenticated(True)
                self.tcp_listener.send_to_client("AUTH_OK")
                logger.info(f"Client authenticated: {client_ip}")
                log_event("connect", f"Client connected: {client_ip}")
            else:
                self.tcp_listener.send_to_client("AUTH_FAIL:ALREADY_CONNECTED")
                log_event("warning", f"Auth rejected (already connected): {client_ip}")
        else:
            self.tcp_listener.send_to_client("AUTH_FAIL:INVALID_CODE")
            log_event("warning", f"Auth failed (invalid code): {client_ip} - received='{code}' expected='{expected_code}'")
    
    def _on_click(self, button: str, state: str):
        """Handle mouse click event."""
        if self.mouse:
            try:
                self.mouse.click(button, state)
            except Exception as e:
                logger.error(f"Click error: {e}")
    
    def _on_key(self, key: str, state: str):
        """Handle keyboard event."""
        if self.keyboard:
            try:
                self.keyboard.key_event(key, state)
            except Exception as e:
                logger.error(f"Key error: {e}")
    
    def _on_move(self, dx: int, dy: int):
        """Handle mouse movement - routes through smoother for interpolation."""
        if self.input_smoother:
            self.input_smoother.add_movement(dx, dy)
    
    def _inject_mouse_move(self, dx: int, dy: int):
        """Actually inject mouse movement (called by smoother)."""
        if self.mouse:
            try:
                self.mouse.move(dx, dy)
            except Exception as e:
                logger.error(f"Move error: {e}")
    
    def _inject_scroll(self, vertical: int, horizontal: int):
        """Actually inject scroll event (called by smoother)."""
        if self.mouse:
            try:
                self.mouse.scroll(vertical, horizontal)
            except Exception as e:
                logger.error(f"Scroll error: {e}")
    
    def _on_scroll(self, vertical: int, horizontal: int):
        """Handle scroll event - routes through smoother."""
        if self.scroll_smoother:
            self.scroll_smoother.add_scroll(vertical, horizontal)
    
    def _on_disconnect(self):
        """Handle client disconnect - regenerates pairing code dynamically."""
        self.connection_manager.disconnect()
        self.auth_manager.reset()
        
        # Generate new pairing code and display dynamically
        new_code = self.auth_manager.generate_code()
        log_event("disconnect", "Client disconnected")
        log_pairing_code(new_code)
        log_status("Waiting for connection...")
    
    def _can_respond_to_discovery(self) -> bool:
        """Check if discovery should respond."""
        return not self.connection_manager.is_connected()
    
    def _is_authorized_client(self, client_ip: str) -> bool:
        """Check if client is authorized for UDP input."""
        return self.connection_manager.is_authorized_client(client_ip)
    
    def start(self):
        """Start the server."""
        check_privileges()
        
        self._local_ip = get_local_ip()
        
        try:
            # Initialize uinput devices
            logger.info("Creating virtual input devices...")
            self.mouse = VirtualMouse()
            self.keyboard = VirtualKeyboard()
            
            # Initialize capacitor-style input smoother
            # Uses optimized parameters for smooth, responsive cursor movement
            self.input_smoother = InputSmoother(
                inject_move=self._inject_mouse_move,
                target_fps=60,
                discharge_rate=0.16,  # Discharge 16% of buffer per frame (smooth)
                continuation_timeout_ms=100,  # 100ms momentum after input stops
                smoothing_factor=0.35,
                velocity_decay=0.65  # 65% decay for precision control
            )
            self.input_smoother.start()
            logger.info("Capacitor smoother started (60 FPS, 16% discharge rate)")
            
            # Initialize scroll smoother with capacitor logic
            self.scroll_smoother = ScrollSmoother(
                inject_scroll=self._inject_scroll,
                target_fps=60,
                discharge_rate=0.12,
                continuation_timeout_ms=150
            )
            self.scroll_smoother.start()
            logger.info("Scroll smoother started (Capacitor logic)")
            
            # Generate pairing code
            pairing_code = self.auth_manager.generate_code()
            
            # Start discovery service
            self.discovery_service = DiscoveryService(
                self._local_ip,
                self._can_respond_to_discovery
            )
            self.discovery_service.start()
            
            # Start UDP input listener
            self.udp_listener = UDPInputListener(
                self._is_authorized_client,
                self._on_move,
                self._on_scroll
            )
            self.udp_listener.start()
            
            # Start TCP control listener
            self.tcp_listener = TCPControlListener(
                self._on_auth,
                self._on_click,
                self._on_key,
                self._on_disconnect
            )
            self.tcp_listener.start()
            
            # Print banner
            print_banner(self._local_ip, pairing_code)
            
            self._running = True
            
            # Wait for shutdown signal
            while self._running:
                signal.pause()
                
        except KeyboardInterrupt:
            print("\n\nShutting down...")
        except Exception as e:
            logger.error(f"Server error: {e}")
            raise
        finally:
            self.stop()
    
    def stop(self):
        """Stop the server and cleanup."""
        self._running = False
        
        logger.info("Stopping server...")
        
        if self.tcp_listener:
            self.tcp_listener.stop()
        
        if self.udp_listener:
            self.udp_listener.stop()
        
        if self.discovery_service:
            self.discovery_service.stop()
        
        if self.input_smoother:
            self.input_smoother.stop()
        
        if self.scroll_smoother:
            self.scroll_smoother.stop()
        
        if self.keyboard:
            self.keyboard.close()
        
        if self.mouse:
            self.mouse.close()
        
        self.connection_manager.disconnect()
        
        logger.info("Server stopped")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="HOTSPOT KEYBOARD & MOUSE - Linux Server"
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable debug logging'
    )
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    server = HotspotKBMServer()
    
    # Handle signals
    def signal_handler(signum, frame):
        server.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    server.start()


if __name__ == "__main__":
    main()
