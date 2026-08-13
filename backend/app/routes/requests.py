import random
from fastapi import APIRouter, HTTPException
from app.database import get_db_connection
from app.schemas import RequestCreate

router = APIRouter(prefix="/api/v1/requests", tags=["Requests"])

def calculate_priority_score(request_type: str, category: str, is_sos: bool, adults: int, children: int, infants: int) -> int:
    score = 0
    if request_type == "EVACUATION" or category.upper() == "EVACUATION":
        score += 100
    elif category.upper() in ["MEDICINE", "DRINKING WATER"]:
        score += 50
    else:
        score += 20
        
    if is_sos:
        score += 50
        
    score += (infants * 10) + (children * 5) + (adults * 2)
    return score

@router.post("")
async def create_request(req: RequestCreate):
    total_people = req.headcount_adults + req.headcount_children + req.headcount_infants
    
    if req.category == "Drinking Water" and req.request_type == "SUPPLY":
        max_allowed = max(total_people * 3, 3)
        if req.quantity_requested > max_allowed:
            raise HTTPException(
                status_code=400, 
                detail=f"Requested water quantity exceeds limit of {max_allowed}L for {total_people} people."
            )

    priority_score = calculate_priority_score(
        request_type=req.request_type.value,
        category=req.category,
        is_sos=req.is_sos,
        adults=req.headcount_adults,
        children=req.headcount_children,
        infants=req.headcount_infants
    )
            
    otp_code = f"{random.randint(1000, 9999)}"
    
    conn = await get_db_connection()
    try:
        request_id = await conn.fetchval(
            """
            INSERT INTO requests (
                requester_id, request_type, category, 
                headcount_adults, headcount_children, headcount_infants, quantity_requested,
                is_missing_person, landmark_notes, is_sos, priority_score,
                created_via, volunteer_id, otp_code, location
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::uuid, $14,
                ST_SetSRID(ST_MakePoint($15, $16), 4326)::geography
            )
            RETURNING id;
            """,
            req.requester_id, req.request_type.value, req.category,
            req.headcount_adults, req.headcount_children, req.headcount_infants, req.quantity_requested,
            req.is_missing_person, req.landmark_notes, req.is_sos, priority_score,
            req.created_via, req.volunteer_id if req.volunteer_id else None, otp_code,
            req.longitude, req.latitude
        )
        return {
            "status": "success", 
            "request_id": str(request_id), 
            "priority_score": priority_score,
            "otp_code": otp_code
        }
    finally:
        await conn.close()