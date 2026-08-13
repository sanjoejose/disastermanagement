from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta, timezone
from app.database import get_db_connection
from app.schemas import SupplyCreate, FoodType

router = APIRouter(prefix="/api/v1/supplies", tags=["Supplies"])

@router.post("")
async def create_supply(supply: SupplyCreate):
    """
    Creates a new supply listing with automated PostGIS Point geometry
    and dynamic expiry timestamp based on perishability.
    """
    now = datetime.now(timezone.utc)
    
    # Calculate expiry duration based on category/food_type
    if supply.food_type == FoodType.COOKED:
        expires_at = now + timedelta(hours=6)
    elif supply.food_type == FoodType.PACKAGED:
        expires_at = now + timedelta(days=30)
    else:
        expires_at = now + timedelta(days=90)  # Default non-perishables/medicine
        
    conn = await get_db_connection()
    try:
        # ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) creates PostGIS geography
        supply_id = await conn.fetchval(
            """
            INSERT INTO supplies (
                supplier_id, category, food_type, quantity, expires_at, location
            )
            VALUES (
                $1, $2, $3, $4, $5, 
                ST_SetSRID(ST_MakePoint($6, $7), 4326)::geography
            )
            RETURNING id;
            """,
            supply.supplier_id, 
            supply.category, 
            supply.food_type.value, 
            supply.quantity, 
            expires_at, 
            supply.longitude, 
            supply.latitude
        )
        return {
            "status": "success", 
            "supply_id": str(supply_id), 
            "expires_at": expires_at.isoformat()
        }
    finally:
        await conn.close()