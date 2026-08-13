import random
from fastapi import APIRouter, HTTPException
from app.database import get_db_connection
from app.schemas import RequestCreate

router = APIRouter(prefix="/api/v1/requests", tags=["Requests"])

@router.post("")
async def create_request(req: RequestCreate):
    """
    Registers a relief request, applies headcount-based capping,
    and generates a delivery OTP code.
    """
    total_people = req.headcount_adults + req.headcount_children
    
    # Anti-Hoarding Cap Rules
    if req.category == "Drinking Water":
        max_allowed = max(total_people * 3, 3)  # Max 3L per person
        if req.quantity_requested > max_allowed:
            raise HTTPException(
                status_code=400, 
                detail=f"Requested water quantity exceeds the limit of {max_allowed}L for {total_people} people."
            )
            
    # Generate random 4-digit OTP
    otp_code = f"{random.randint(1000, 9999)}"
    
    conn = await get_db_connection()
    try:
        request_id = await conn.fetchval(
            """
            INSERT INTO requests (
                requester_id, headcount_adults, headcount_children, headcount_infants,
                category, quantity_requested, is_sos, otp_code, location
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8,
                ST_SetSRID(ST_MakePoint($9, $10), 4326)::geography
            )
            RETURNING id;
            """,
            req.requester_id, req.headcount_adults, req.headcount_children, req.headcount_infants,
            req.category, req.quantity_requested, req.is_sos, otp_code,
            req.longitude, req.latitude
        )
        return {
            "status": "success", 
            "request_id": str(request_id), 
            "otp_code": otp_code
        }
    finally:
        await conn.close()