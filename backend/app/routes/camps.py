from fastapi import APIRouter, HTTPException
from app.database import get_db_connection
from app.schemas import CampCreate

router = APIRouter(prefix="/api/v1/camps", tags=["Camps"])

@router.post("")
async def create_camp(camp: CampCreate):
    """Registers a new active Relief Camp / Shelter."""
    conn = await get_db_connection()
    try:
        camp_id = await conn.fetchval(
            """
            INSERT INTO camps (name, contact_person, contact_phone, max_capacity, has_medical_facility, has_food_supply, location)
            VALUES ($1, $2, $3, $4, $5, $6, ST_SetSRID(ST_MakePoint($7, $8), 4326)::geography)
            RETURNING id;
            """,
            camp.name, camp.contact_person, camp.contact_phone, camp.max_capacity,
            camp.has_medical_facility, camp.has_food_supply, camp.longitude, camp.latitude
        )
        return {"status": "success", "camp_id": str(camp_id)}
    finally:
        await conn.close()

@router.get("")
async def get_all_active_camps():
    """Lists all active relief camps globally for admin monitoring."""
    conn = await get_db_connection()
    try:
        camps = await conn.fetch(
            """
            SELECT id, name, contact_person, contact_phone, max_capacity, current_occupancy,
                   has_medical_facility, has_food_supply,
                   ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon
            FROM camps
            WHERE is_active = TRUE
            ORDER BY created_at DESC;
            """
        )
        return {"status": "success", "camps": [dict(c) for c in camps]}
    finally:
        await conn.close()