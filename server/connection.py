"""
Connection manager for single-client enforcement.
"""

import threading
import socket
from typing import Optional, Tuple


class ConnectionManager:
    """
    Manages client connections with single-client enforcement.
    
    Only one client can be connected at a time. New connection
    attempts are rejected when a client is already connected.
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        self._active_client_ip: Optional[str] = None
        self._active_client_socket: Optional[socket.socket] = None
        self._connected = False
    
    def try_connect(self, client_ip: str, client_socket: socket.socket) -> bool:
        """
        Attempt to register a new client connection.
        
        Returns True if the connection was accepted (no other client connected).
        Returns False if rejected (another client is already connected).
        """
        with self._lock:
            if self._connected:
                return False
            
            self._active_client_ip = client_ip
            self._active_client_socket = client_socket
            self._connected = True
            return True
    
    def disconnect(self):
        """Disconnect the current client and allow new connections."""
        with self._lock:
            if self._active_client_socket:
                try:
                    self._active_client_socket.close()
                except:
                    pass
            
            self._active_client_ip = None
            self._active_client_socket = None
            self._connected = False
    
    def is_connected(self) -> bool:
        """Check if a client is currently connected."""
        with self._lock:
            return self._connected
    
    def is_authorized_client(self, client_ip: str) -> bool:
        """Check if the given IP is the authorized client."""
        with self._lock:
            return self._connected and self._active_client_ip == client_ip
    
    @property
    def active_client(self) -> Optional[Tuple[str, socket.socket]]:
        """Get the active client info (IP, socket) or None."""
        with self._lock:
            if self._connected:
                return (self._active_client_ip, self._active_client_socket)
            return None
    
    @property
    def active_client_ip(self) -> Optional[str]:
        """Get the active client IP or None."""
        with self._lock:
            return self._active_client_ip
