"""
Authentication module for 6-digit pairing code.
"""

import random
import string
import time
from typing import Optional

from .config import AUTH_CODE_LENGTH, AUTH_TIMEOUT


class AuthManager:
    """
    Manages the 6-digit pairing authentication flow.
    
    The pairing code is displayed on the server console and must be
    entered on the Android client to establish a connection.
    """
    
    def __init__(self):
        self._code: Optional[str] = None
        self._generated_at: Optional[float] = None
        self._authenticated = False
    
    def generate_code(self) -> str:
        """Generate a new 6-digit pairing code."""
        self._code = ''.join(random.choices(string.digits, k=AUTH_CODE_LENGTH))
        self._generated_at = time.time()
        self._authenticated = False
        return self._code
    
    def validate_code(self, input_code: str) -> bool:
        """
        Validate the provided code against the generated one.
        
        Returns True if:
        - A code has been generated
        - The code hasn't expired
        - The input matches the generated code
        """
        if self._code is None or self._generated_at is None:
            return False
        
        # Check timeout
        if time.time() - self._generated_at > AUTH_TIMEOUT:
            self._code = None
            self._generated_at = None
            return False
        
        # Validate code
        if input_code.strip() == self._code:
            self._authenticated = True
            return True
        
        return False
    
    @property
    def is_authenticated(self) -> bool:
        """Check if a client has been authenticated."""
        return self._authenticated
    
    @property
    def current_code(self) -> Optional[str]:
        """Get the current pairing code (for display)."""
        return self._code
    
    def reset(self):
        """Reset authentication state."""
        self._code = None
        self._generated_at = None
        self._authenticated = False
