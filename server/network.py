"""
Network listeners for UDP (mouse/scroll) and TCP (control/auth) protocols.
"""

import socket
import threading
import logging
from typing import Optional, Callable, Tuple

from .config import INPUT_PORT, CONTROL_PORT, BUTTON_MAP, KEY_MAP

logger = logging.getLogger(__name__)


class UDPInputListener:
    """
    UDP listener for mouse movement and scroll events.
    
    Packet format:
        MOVE <dx> <dy>
        SCROLL <v> <h>
    """
    
    def __init__(
        self,
        is_authorized: Callable[[str], bool],
        on_move: Callable[[int, int], None],
        on_scroll: Callable[[int, int], None]
    ):
        """
        Initialize the UDP input listener.
        
        Args:
            is_authorized: Callback to check if client IP is authorized
            on_move: Callback for mouse movement (dx, dy)
            on_scroll: Callback for scroll events (vertical, horizontal)
        """
        self._is_authorized = is_authorized
        self._on_move = on_move
        self._on_scroll = on_scroll
        
        self._socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
    
    def _parse_packet(self, data: bytes) -> Optional[Tuple[str, int, int]]:
        """Parse a UDP packet into (command, val1, val2)."""
        try:
            message = data.decode('utf-8', errors='ignore').strip()
            parts = message.split()
            
            if len(parts) == 3:
                cmd = parts[0].upper()
                val1 = int(parts[1])
                val2 = int(parts[2])
                return (cmd, val1, val2)
        except (ValueError, IndexError):
            pass
        return None
    
    def _listen_loop(self):
        """Main UDP listening loop."""
        while self._running:
            try:
                data, addr = self._socket.recvfrom(256)
                client_ip = addr[0]
                
                # Check authorization
                if not self._is_authorized(client_ip):
                    continue
                
                parsed = self._parse_packet(data)
                if parsed is None:
                    continue
                
                cmd, val1, val2 = parsed
                
                if cmd == "MOVE":
                    self._on_move(val1, val2)
                elif cmd == "SCROLL":
                    self._on_scroll(val1, val2)
                    
            except socket.timeout:
                continue
            except OSError as e:
                if self._running:
                    logger.error(f"UDP socket error: {e}")
                break
    
    def start(self):
        """Start the UDP listener."""
        if self._running:
            return
        
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.settimeout(1.0)
        self._socket.bind(('', INPUT_PORT))
        
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        
        logger.info(f"UDP input listener started on port {INPUT_PORT}")
    
    def stop(self):
        """Stop the UDP listener."""
        self._running = False
        
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
            self._socket = None
        
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        
        logger.info("UDP input listener stopped")


class TCPControlListener:
    """
    TCP listener for authentication, clicks, and keyboard events.
    
    Packet format:
        AUTH <code>
        CLICK <button> <state>
        KEY <state> <keycode>
    """
    
    def __init__(
        self,
        on_auth: Callable[[socket.socket, str, str], None],
        on_click: Callable[[str, str], None],
        on_key: Callable[[str, str], None],
        on_disconnect: Callable[[], None]
    ):
        """
        Initialize the TCP control listener.
        
        Args:
            on_auth: Callback for auth attempt (socket, client_ip, code)
            on_click: Callback for click events (button, state)
            on_key: Callback for key events (key, state)
            on_disconnect: Callback when client disconnects
        """
        self._on_auth = on_auth
        self._on_click = on_click
        self._on_key = on_key
        self._on_disconnect = on_disconnect
        
        self._socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._client_thread: Optional[threading.Thread] = None
        self._running = False
        self._client_socket: Optional[socket.socket] = None
        self._authenticated = False
    
    def _handle_client(self, client_socket: socket.socket, client_addr: Tuple[str, int]):
        """Handle a connected client."""
        client_ip = client_addr[0]
        logger.info(f"TCP client connected: {client_ip}")
        
        self._client_socket = client_socket
        buffer = ""
        
        try:
            while self._running:
                try:
                    data = client_socket.recv(1024)
                    if not data:
                        break
                    
                    buffer += data.decode('utf-8', errors='ignore')
                    
                    # Process complete lines
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        self._process_command(client_socket, client_ip, line.strip())
                        
                except socket.timeout:
                    continue
                except OSError:
                    break
                    
        except Exception as e:
            logger.error(f"Client handler error: {e}")
        finally:
            logger.info(f"TCP client disconnected: {client_ip}")
            self._authenticated = False
            self._client_socket = None
            try:
                client_socket.close()
            except:
                pass
            self._on_disconnect()
    
    def _process_command(self, client_socket: socket.socket, client_ip: str, command: str):
        """Process a single command from the client."""
        if not command:
            return
        
        parts = command.split()
        if not parts:
            return
        
        cmd = parts[0].upper()
        
        if cmd == "AUTH" and len(parts) >= 2:
            code = parts[1]
            self._on_auth(client_socket, client_ip, code)
            
        elif self._authenticated:
            if cmd == "CLICK" and len(parts) >= 3:
                button = parts[1].upper()
                state = parts[2].upper()
                if button in BUTTON_MAP and state in ("DOWN", "UP"):
                    self._on_click(button, state)
                    
            elif cmd == "KEY" and len(parts) >= 3:
                state = parts[1].upper()
                key = parts[2].upper()
                if key in KEY_MAP and state in ("DOWN", "UP"):
                    self._on_key(key, state)
    
    def set_authenticated(self, authenticated: bool):
        """Set the authentication state."""
        self._authenticated = authenticated
    
    def send_to_client(self, message: str):
        """Send a message to the connected client."""
        if self._client_socket:
            try:
                self._client_socket.send((message + "\n").encode('utf-8'))
            except:
                pass
    
    def _accept_loop(self):
        """Main TCP accept loop."""
        while self._running:
            try:
                client_socket, client_addr = self._socket.accept()
                client_socket.settimeout(1.0)
                
                # Handle client in a separate thread
                self._client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, client_addr),
                    daemon=True
                )
                self._client_thread.start()
                
                # Wait for this client to disconnect before accepting new ones
                self._client_thread.join()
                
            except socket.timeout:
                continue
            except OSError as e:
                if self._running:
                    logger.error(f"TCP accept error: {e}")
                break
    
    def start(self):
        """Start the TCP listener."""
        if self._running:
            return
        
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.settimeout(1.0)
        self._socket.bind(('', CONTROL_PORT))
        self._socket.listen(1)
        
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()
        
        logger.info(f"TCP control listener started on port {CONTROL_PORT}")
    
    def stop(self):
        """Stop the TCP listener."""
        self._running = False
        
        if self._client_socket:
            try:
                self._client_socket.close()
            except:
                pass
            self._client_socket = None
        
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
            self._socket = None
        
        if self._client_thread:
            self._client_thread.join(timeout=2.0)
        if self._thread:
            self._thread.join(timeout=2.0)
        
        logger.info("TCP control listener stopped")
