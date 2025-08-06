import secrets
import string
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User


class InvitationService:
    """Service for managing invitation codes."""
    
    # In production, these would be stored in a database
    # For now, using a simple in-memory store with some predefined codes
    VALID_CODES = {
        "CHEF2024": {"role": "chef", "expires": None},
        "FAMILY24": {"role": "family_member", "expires": None},
        "DEMO1234": {"role": "family_member", "expires": None},
        # Add more codes as needed
    }
    
    @classmethod
    async def validate_invitation_code(
        cls, 
        code: str, 
        db: AsyncSession
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Validate an invitation code.
        
        Returns:
            tuple: (is_valid, role, error_message)
        """
        code = code.upper().strip()
        
        # Check if code exists
        if code not in cls.VALID_CODES:
            return False, None, "Invalid invitation code"
        
        code_info = cls.VALID_CODES[code]
        
        # Check if code has expired
        if code_info["expires"]:
            if datetime.utcnow() > code_info["expires"]:
                return False, None, "This invitation code has expired"
        
        # Check if code has already been used (optional - for single-use codes)
        # In production, you might want to track usage in the database
        result = await db.execute(
            select(User).where(User.invitation_code == code)
        )
        existing_users = result.scalars().all()
        
        # For demo purposes, allow multiple uses of the same code
        # In production, you might want to limit this
        # if len(existing_users) >= 1:
        #     return False, None, "This invitation code has already been used"
        
        return True, code_info["role"], None
    
    @classmethod
    def generate_invitation_code(cls, length: int = 8) -> str:
        """Generate a random invitation code."""
        characters = string.ascii_uppercase + string.digits
        return ''.join(secrets.choice(characters) for _ in range(length))
    
    @classmethod
    def add_invitation_code(
        cls, 
        code: str, 
        role: str, 
        expires_in_days: Optional[int] = None
    ) -> None:
        """Add a new invitation code (for admin use)."""
        expires = None
        if expires_in_days:
            expires = datetime.utcnow() + timedelta(days=expires_in_days)
        
        cls.VALID_CODES[code.upper()] = {
            "role": role,
            "expires": expires
        }