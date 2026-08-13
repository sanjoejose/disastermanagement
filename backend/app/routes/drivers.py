import math
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.database import get_db_connection

router = APIRouter(prefix="/api/v1/drivers", tags=["Drivers"])


# --- PYDANTIC SCHEMAS ---
class AcceptRoutePayload(BaseModel):
    driver_id: str = Field(..., description="UUID of the driver accepting the route")
    supply_id: str = Field(..., description="UUID of the supply listing being picked up")
    request_id: str = Field(..., description="UUID of the relief/evacuation request")


# --- ENDPOINTS ---

@router.get("/discover-nearby")
async def discover_nearby_supplies_and_evacuations(
    driver_lat: float = Query(..., ge=-90.0, le=90.0, example=9.9661, description="Driver's current latitude"),
    driver_lon: float = Query(..., ge=-180.0, le=180.0, example=76.3190, description="Driver's current longitude"),
    radius_km: float = Query(5.0, ge=1.0, le=50.0, description="Search radius in kilometers around driver")
):
    """
    1. Driver-Centric Discovery (Evacuations First!):
    Scans the driver's vicinity for both active EVACUATION requests 
    and AVAILABLE supply hubs, giving immediate priority to life safety.
    """
    radius_meters = radius_km * 1000.0
    conn = await get_db_connection()
    try:
        # A. Fetch nearby urgent EVACUATION requests within radius
        evacuations_nearby = await conn.fetch(
            """
            SELECT 
                r.id AS request_id,
                r.category,
                r.headcount_adults,
                r.headcount_children,
                r.headcount_infants,
                (r.headcount_adults + r.headcount_children + r.headcount_infants) AS total_headcount,
                r.is_sos,
                r.is_missing_person,
                r.landmark_notes,
                r.priority_score,
                u.full_name AS requester_name,
                u.phone_number AS requester_phone,
                ST_Y(r.location::geometry) AS lat,
                ST_X(r.location::geometry) AS lon,
                ST_Distance(
                    r.location, 
                    ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography
                ) AS distance_meters
            FROM requests r
            JOIN users u ON r.requester_id = u.id
            WHERE r.status = 'PENDING'
              AND r.request_type = 'EVACUATION'
              AND ST_DWithin(
                  r.location, 
                  ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, 
                  $3
              )
            ORDER BY r.is_sos DESC, r.priority_score DESC, distance_meters ASC;
            """,
            driver_lon, driver_lat, radius_meters
        )

        formatted_evacuations = []
        for e in evacuations_nearby:
            ed = dict(e)
            ed["distance_km"] = round(e["distance_meters"] / 1000, 2)
            ed["phone_call_link"] = f"tel:{e['requester_phone']}"
            formatted_evacuations.append(ed)

        # B. Fetch nearby active supply hubs
        supplies_nearby = await conn.fetch(
            """
            SELECT 
                s.id AS supply_id,
                s.supplier_id,
                s.category,
                s.food_type,
                s.quantity,
                s.expires_at,
                u.full_name AS supplier_name,
                u.phone_number AS supplier_phone,
                ST_Y(s.location::geometry) AS supply_lat,
                ST_X(s.location::geometry) AS supply_lon,
                ST_Distance(
                    s.location, 
                    ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography
                ) AS distance_meters
            FROM supplies s
            JOIN users u ON s.supplier_id = u.id
            WHERE s.status = 'AVAILABLE' 
              AND s.expires_at > CURRENT_TIMESTAMP
              AND ST_DWithin(
                  s.location, 
                  ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, 
                  $3
              )
            ORDER BY distance_meters ASC;
            """,
            driver_lon, driver_lat, radius_meters
        )

        formatted_supplies = []
        for sup in supplies_nearby:
            s_dict = dict(sup)
            s_dict["distance_km"] = round(sup["distance_meters"] / 1000, 2)
            s_dict["expires_at"] = sup["expires_at"].isoformat()
            formatted_supplies.append(s_dict)

        return {
            "status": "success",
            "driver_location": {"lat": driver_lat, "lon": driver_lon},
            "has_urgent_evacuations": len(formatted_evacuations) > 0,
            "evacuation_count": len(formatted_evacuations),
            "supply_hub_count": len(formatted_supplies),
            "nearby_evacuations": formatted_evacuations,
            "nearby_supplies": formatted_supplies
        }
    finally:
        await conn.close()


@router.get("/nearby-routes")
async def get_nearby_routes(
    supplier_id: str,
    radius_km: float = Query(5.0, ge=1.0, le=50.0, description="Search radius in kilometers")
):
    """
    2. Direction-Vector Route Generation (ST_Azimuth Cone Filtering):
    Anchors the single highest-priority request (Wait time + SOS + Headcount - Distance)
    and filters subsequent waypoints into a single 90-degree directional vector cone.
    """
    conn = await get_db_connection()
    try:
        supply = await conn.fetchrow(
            """
            SELECT id, category, food_type, quantity, expires_at,
                   ST_Y(location::geometry) AS lat,
                   ST_X(location::geometry) AS lon
            FROM supplies
            WHERE supplier_id = $1::uuid AND status = 'AVAILABLE' AND expires_at > CURRENT_TIMESTAMP
            ORDER BY created_at DESC
            LIMIT 1;
            """,
            supplier_id
        )

        if not supply:
            raise HTTPException(status_code=404, detail="No active, unexpired supplies found for this supplier.")

        s_lat = supply['lat']
        s_lon = supply['lon']
        category = supply['category']
        food_type = supply['food_type']

        radius_meters = radius_km * 1000.0
        if food_type == 'COOKED' and radius_km > 5.0:
            radius_meters = 5000.0

        requests = await conn.fetch(
            """
            WITH anchor_request AS (
                SELECT 
                    r.id AS anchor_id,
                    r.location AS anchor_loc,
                    ST_Azimuth(
                        ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, 
                        r.location
                    ) AS anchor_angle
                FROM requests r
                WHERE r.status = 'PENDING'
                  AND (r.category = $3 OR r.request_type = 'EVACUATION')
                  AND ST_DWithin(r.location, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, $4)
                ORDER BY (
                    r.priority_score 
                    + (EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - r.created_at)) / 1800 * 5)
                    - (ST_Distance(r.location, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography) / 1000 * 2)
                ) DESC
                LIMIT 1
            )
            SELECT 
                r.id AS request_id, 
                r.request_type, 
                r.category, 
                r.quantity_requested, 
                r.headcount_adults, 
                r.headcount_children, 
                r.headcount_infants, 
                r.is_sos, 
                r.landmark_notes,
                u.full_name AS requester_name, 
                u.phone_number AS requester_phone,
                ST_Y(r.location::geometry) AS lat, 
                ST_X(r.location::geometry) AS lon,
                ST_Distance(r.location, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography) / 1000 AS distance_km,
                (
                    r.priority_score 
                    + (EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - r.created_at)) / 1800 * 5)
                    - (ST_Distance(r.location, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography) / 1000 * 2)
                ) AS dynamic_score
            FROM requests r
            CROSS JOIN anchor_request a
            JOIN users u ON r.requester_id = u.id
            WHERE r.status = 'PENDING'
              AND (r.category = $3 OR r.request_type = 'EVACUATION')
              AND ST_DWithin(r.location, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, $4)
              AND (
                  ABS(ST_Azimuth(ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, r.location) - a.anchor_angle) < 0.785
                  OR ABS(ST_Azimuth(ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, r.location) - a.anchor_angle) > (2 * PI() - 0.785)
              )
            ORDER BY distance_km ASC
            LIMIT 5;
            """,
            s_lon, s_lat, category, radius_meters
        )

        if not requests:
            return {
                "status": "success",
                "message": "No matching pending requests within range.",
                "supply_info": {
                    "supply_id": str(supply["id"]),
                    "category": supply["category"],
                    "quantity": supply["quantity"]
                },
                "matched_requests": []
            }

        origin = f"{s_lat},{s_lon}"
        destination = f"{requests[-1]['lat']},{requests[-1]['lon']}"
        
        waypoints_str = ""
        if len(requests) > 1:
            waypoint_coords = [f"{r['lat']},{r['lon']}" for r in requests[:-1]]
            waypoints_str = f"&waypoints={'|'.join(waypoint_coords)}"

        google_maps_url = (
            f"https://www.google.com/maps/dir/?api=1"
            f"&origin={quote(origin)}"
            f"&destination={quote(destination)}"
            f"{waypoints_str}"
            f"&travelmode=driving"
        )

        formatted_requests = []
        for r in requests:
            req_dict = dict(r)
            req_dict["distance_km"] = round(r["distance_km"], 2)
            req_dict["dynamic_score"] = round(r["dynamic_score"], 2)
            req_dict["phone_call_link"] = f"tel:{r['requester_phone']}"
            formatted_requests.append(req_dict)

        return {
            "status": "success",
            "supply_id": str(supply["id"]),
            "matched_count": len(requests),
            "google_maps_navigation_url": google_maps_url,
            "requests": formatted_requests
        }

    finally:
        await conn.close()


@router.get("/nearest-camp")
async def get_nearest_camp(
    pickup_lat: float = Query(..., ge=-90.0, le=90.0),
    pickup_lon: float = Query(..., ge=-180.0, le=180.0)
):
    """
    3. Relief Camp Auto-Routing:
    Finds the nearest active relief camp with open capacity from the pickup point.
    """
    conn = await get_db_connection()
    try:
        camp = await conn.fetchrow(
            """
            SELECT 
                id, name, contact_person, contact_phone, max_capacity, current_occupancy,
                (max_capacity - current_occupancy) AS available_space,
                ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon,
                ST_Distance(
                    location, 
                    ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography
                ) / 1000 AS distance_km
            FROM camps
            WHERE is_active = TRUE AND current_occupancy < max_capacity
            ORDER BY location <-> ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography
            LIMIT 1;
            """,
            pickup_lon, pickup_lat
        )

        if not camp:
            raise HTTPException(status_code=404, detail="No active relief camps with available capacity found nearby.")

        cd = dict(camp)
        origin = f"{pickup_lat},{pickup_lon}"
        destination = f"{camp['lat']},{camp['lon']}"
        cd["navigation_url"] = f"https://www.google.com/maps/dir/?api=1&origin={quote(origin)}&destination={quote(destination)}&travelmode=driving"
        
        return {"status": "success", "recommended_camp": cd}
    finally:
        await conn.close()


@router.post("/accept-route")
async def accept_route(payload: AcceptRoutePayload):
    """
    4. Route Lock & Inventory Deduction:
    Transitions request status to 'IN_TRANSIT' and deducts stock inside an isolated transaction.
    """
    conn = await get_db_connection()
    async with conn.transaction():
        supply = await conn.fetchrow("SELECT quantity, status FROM supplies WHERE id = $1::uuid FOR UPDATE;", payload.supply_id)
        request = await conn.fetchrow("SELECT quantity_requested, status, request_type FROM requests WHERE id = $1::uuid FOR UPDATE;", payload.request_id)

        if not supply or supply["status"] != "AVAILABLE":
            raise HTTPException(status_code=400, detail="Supply is no longer available.")
        if not request or request["status"] != "PENDING":
            raise HTTPException(status_code=400, detail="Request has already been accepted by another driver or cancelled.")

        if request["request_type"] == "SUPPLY":
            if supply["quantity"] < request["quantity_requested"]:
                raise HTTPException(status_code=400, detail="Insufficient supply stock.")
            new_qty = supply["quantity"] - request["quantity_requested"]
            new_status = "CLAIMED" if new_qty == 0 else "AVAILABLE"
            await conn.execute("UPDATE supplies SET quantity = $1, status = $2 WHERE id = $3::uuid;", new_qty, new_status, payload.supply_id)

        await conn.execute("UPDATE requests SET status = 'IN_TRANSIT', updated_at = CURRENT_TIMESTAMP WHERE id = $1::uuid;", payload.request_id)
        return {"status": "success", "message": "Route accepted successfully! Request is now IN_TRANSIT."}


@router.post("/verify-delivery")
async def verify_delivery(
    request_id: str, 
    input_otp: str, 
    rescued_count: int = Query(0, description="Actual number of persons rescued (if evacuation)")
):
    """
    5. OTP Delivery / Evacuation Verification:
    Validates recipient PIN and updates request status to FULFILLED.
    """
    conn = await get_db_connection()
    try:
        req = await conn.fetchrow(
            """
            SELECT otp_code, (headcount_adults + headcount_children + headcount_infants) AS total_people 
            FROM requests 
            WHERE id = $1::uuid;
            """, 
            request_id
        )
        if not req:
            raise HTTPException(status_code=404, detail="Request ID not found.")
        if req["otp_code"] != input_otp:
            raise HTTPException(status_code=400, detail="Invalid OTP code. Verification failed.")

        total_rescued = rescued_count if rescued_count > 0 else req["total_people"]

        await conn.execute(
            """
            UPDATE requests 
            SET status = 'FULFILLED', headcount_rescued = $1, updated_at = CURRENT_TIMESTAMP 
            WHERE id = $2::uuid;
            """,
            total_rescued, request_id
        )
        return {"status": "success", "message": "Delivery/Evacuation verified and marked as FULFILLED!"}
    finally:
        await conn.close()