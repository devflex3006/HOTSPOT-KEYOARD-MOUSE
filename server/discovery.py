"""
UDP Discovery service for client auto-detection.
"""

import socket
import threading
import logging
from typing import Optional, Callable

from .config import (
    DISCOVERY_PORT, CONTROL_PORT,
    DISCOVERY_MAGIC, SERVER_RESPONSE_PREFIX, SERVER_NAME
)

logger = logging.getLogger(__name__)


class DiscoveryService:
    """
    UDP-based discovery service.
    
    Listens for discovery broadcast packets from Android clients
    and responds with server information.
    """
    
    def __init__(self, server_ip: str, can_respond: Callable[[], bool]):
        """
        Initialize the discovery service.
        
        Args:
            server_ip: The server's IP address to advertise
            can_respond: Callback that returns True if discovery should respond
                        (False when a client is already connected)
        """
        self.server_ip = server_ip
        self._can_respond = can_respond
        self._socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
    
    def _build_response(self) -> bytes:
        """Build the discovery response message."""
        response = "\n".join([
            SERVER_RESPONSE_PREFIX,
            SERVER_NAME,
            self.server_ip,
            str(CONTROL_PORT),
            "AUTH_REQUIRED=true"
        ])
        return response.encode('utf-8')
    
    def _listen_loop(self):
        """Main discovery listening loop."""
        while self._running:
            try:
                data, addr = self._socket.recvfrom(1024)
                message = data.decode('utf-8', errors='ignore').strip()
                
                logger.debug(f"Discovery packet from {addr}: {message}")
                
                if message == DISCOVERY_MAGIC:
                    # Only respond if no client is connected
                    if self._can_respond():
                        response = self._build_response()
                        self._socket.sendto(response, addr)
                        logger.info(f"Sent discovery response to {addr}")
                    else:
                        logger.debug(f"Ignoring discovery (client already connected)")
                        
            except socket.timeout:
                continue
            except OSError as e:
                if self._running:
                    logger.error(f"Discovery socket error: {e}")
                break
    
    def start(self):
        """Start the discovery service."""
        if self._running:
            return
        
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._socket.settimeout(1.0)
        self._socket.bind(('', DISCOVERY_PORT))
        
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        
        logger.info(f"Discovery service started on port {DISCOVERY_PORT}")
    
    def stop(self):
        """Stop the discovery service."""
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
        
        logger.info("Discovery service stopped")
