from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

class UserRole(str, Enum):
    REQUESTER = "requester"
    SUPPLIER = "supplier"
    DRIVER = "driver"
    ADMIN = "admin"
    HOTLINE_VOLUNTEER = "hotline_volunteer"
    MILITARY_ERT = "military_ert"
    GOVT_LEADER = "govt_leader"

class RequestType(str, Enum):
    EVACUATION = "EVACUATION"
    SUPPLY = "SUPPLY"

class FoodType(str, Enum):
    COOKED = "COOKED"
    PACKAGED = "PACKAGED"
    NON_FOOD = "NON_FOOD"

# --- USER SCHEMAS ---
class UserCreate(BaseModel):
    full_name: str = Field(..., min_length=2)
    phone_number: str = Field(..., min_length=10, max_length=15)
    role: UserRole

# --- SUPPLY SCHEMAS ---
class SupplyCreate(BaseModel):
    supplier_id: str
    category: str
    food_type: FoodType = FoodType.NON_FOOD
    quantity: int = Field(..., gt=0)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)

class SupplyUpdate(BaseModel):
    quantity: Optional[int] = None
    status: Optional[str] = None # 'AVAILABLE', 'EXPIRED_EARLY', 'DISTRIBUTED_OFFLINE', 'CANCELLED'

# --- REQUEST SCHEMAS ---
class RequestCreate(BaseModel):
    requester_id: str
    request_type: RequestType = RequestType.SUPPLY
    category: str  # 'EVACUATION', 'Prepared Meals', 'Drinking Water', 'Medicine'
    headcount_adults: int = Field(1, ge=0)
    headcount_children: int = Field(0, ge=0)
    headcount_infants: int = Field(0, ge=0)
    quantity_requested: int = Field(1, ge=1)
    is_sos: bool = False
    is_missing_person: bool = False
    landmark_notes: Optional[str] = None
    created_via: Optional[str] = "APP_DIRECT" # 'APP_DIRECT' or 'HOTLINE_VOLUNTEER'
    volunteer_id: Optional[str] = None
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)

# --- CAMP SCHEMAS ---
class CampCreate(BaseModel):
    name: str
    contact_person: Optional[str] = None
    contact_phone: str
    max_capacity: int = Field(100, gt=0)
    has_medical_facility: bool = False
    has_food_supply: bool = True
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)