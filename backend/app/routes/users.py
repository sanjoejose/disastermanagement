from fastapi import APIRouter, HTTPException
from app.database import get_db_connection
from app.schemas import UserCreate

router = APIRouter(prefix="/api/v1/users", tags=["Users"])

@router.post("")
async def create_user(user: UserCreate):
    """Register a new user in the system."""
    conn = await get_db_connection()
    try:
        user_id = await conn.fetchval(
            """
            INSERT INTO users (full_name, phone_number, role)
            VALUES ($1, $2, $3)
            RETURNING id;
            """,
            user.full_name, user.phone_number, user.role.value
        )
        return {"status": "success", "user_id": str(user_id)}
    finally:
        await conn.close()