from fastapi import APIRouter, HTTPException, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from database import get_database, employee_collection, admins_collection, orders_collection, sales_collection
from security import get_current_admin
from datetime import datetime, timezone
from bson import ObjectId




router = APIRouter()

def convert_objectid_to_str(document):
    """Recursively converts ObjectId fields in a document to strings."""
    if isinstance(document, dict):
        for key, value in document.items():
            if isinstance(value, ObjectId):
                document[key] = str(value)
            elif isinstance(value, list):  
                document[key] = [str(v) if isinstance(v, ObjectId) else v for v in value]
    return document


@router.post("/admin/create-employee")
async def create_employee(
    email: str, 
    name: str, 
    db: AsyncIOMotorDatabase = Depends(get_database), 
    admin: dict = Depends(get_current_admin)  # Ensure admin is passed
):
    """Admin creates an employee with email, name, and organization details"""

    # Ensure admin has an ObjectId
    try:
        admin_id = ObjectId(admin["admin_id"])  # Convert token's admin_id to ObjectId
        admin_data = await admins_collection.find_one({"_id": admin_id})
        
        if not admin_data:
            raise HTTPException(status_code=404, detail="Admin not found")
            
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Admin ID format")

    # Fetch organization details
    org_id = admin_data.get("organization_id")  # Ensure admin has organization_id
    org_name = admin_data.get("organization")
    emp_limit = admin_data.get("emp_count", 0)

    if not org_id or not org_name:
        raise HTTPException(status_code=400, detail="Organization details missing for admin")

    # Check current employee count under this organization
    current_emp_count = await employee_collection.count_documents({"organization_id": org_id})

    # **Check if adding this employee will exceed the limit**
    if current_emp_count >= emp_limit:
        raise HTTPException(status_code=403, detail=f"Employee limit reached ({emp_limit}). Cannot add more employees.")

    # Check if the employee already exists
    existing_employee = await employee_collection.find_one({"email": email})
    if existing_employee:
        raise HTTPException(status_code=400, detail="Employee already exists")

    # Create new employee
    employee_data = {
        "email": email,
        "name": name,
        "organization_id": org_id,
        "organization": org_name,
        "created_at": datetime.now(timezone.utc),  
        "admin_id": admin_id,
        "role": "employee"
    }

    # Insert employee into the database
    new_employee = await employee_collection.insert_one(employee_data)

    # **✅ Auto-update total employees in the organization collection**
    await db["organizations"].update_one(
        {"_id": ObjectId(org_id)}, 
        {"$inc": {"total_employees": 1}}  # Increment employee count
    )

    return {
        "message": "Employee created successfully",
        "employee_id": str(new_employee.inserted_id),
        "organization_id": org_id,
        "organization_name": org_name,
        "created_at": employee_data["created_at"]
    }

    
    
@router.get("/admin/employees", status_code=200)
async def get_employees(
    is_active: bool = Query(None, description="Filter by active status (true/false)"),
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Employees per page (max 100)"),
    admin: dict = Depends(get_current_admin)  # Ensures only admins can access
):
    """
    Get a paginated list of employees with their active status.
    Only admins can access this endpoint.
    """
    admin_id = admin.get("admin_id")
    if not admin_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Start with an empty query to fetch all employees
    query = {}

    # Apply active status filter if provided
    if is_active is not None:
        query["is_active"] = is_active

    # Pagination logic
    skip = (page - 1) * page_size
    total_employees = await employee_collection.count_documents(query)

    # Fetch paginated employees
    employees_cursor = employee_collection.find(query).skip(skip).limit(page_size)
    employees = await employees_cursor.to_list(length=page_size)

    # Convert ObjectId fields to strings
    for employee in employees:
        employee["_id"] = str(employee["_id"])

    return {
        "employees": employees,
        "total_employees": total_employees,
        "page": page,
        "page_size": page_size,
        "total_pages": (total_employees + page_size - 1) // page_size,  # Round up
    }
    
@router.get("/admin/orders", status_code=200)
async def get_orders(
    employee_id: str = Query(None, description="Filter by Employee ID"),
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Orders per page (max 100)"),
    admin: dict = Depends(get_current_admin)  # Ensures only admins can access
):
    """
    Get a paginated list of orders placed by employees.
    Only admins can access this endpoint.
    """
    admin_id = admin.get("admin_id")
    if not admin_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Start with an empty query to fetch all orders
    query = {}

    # Apply Employee ID filter if provided
    if employee_id:
        try:
            query["employee_id"] = ObjectId(employee_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid Employee ID format")

    # Pagination logic
    skip = (page - 1) * page_size
    total_orders = await orders_collection.count_documents(query)

    # Fetch paginated orders
    orders_cursor = orders_collection.find(query).skip(skip).limit(page_size)
    orders = await orders_cursor.to_list(length=page_size)

    # Convert ObjectId fields to strings
    for order in orders:
        order["_id"] = str(order["_id"])
        order["employee_id"] = str(order["employee_id"])

    return {
        "orders": orders,
        "total_orders": total_orders,
        "page": page,
        "page_size": page_size,
        "total_pages": (total_orders + page_size - 1) // page_size,  # Round up
    }  
    
@router.get("/admin/sales", status_code=200)
async def get_sales(
    employee_id: str = Query(None, description="Filter by Employee ID"),
    start_date: str = Query(None, description="Filter sales from this date (YYYY-MM-DD)"),
    end_date: str = Query(None, description="Filter sales up to this date (YYYY-MM-DD)"),
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Sales per page (max 100)"),
    admin: dict = Depends(get_current_admin)  # Ensures only admins can access
):
    """
    Get a paginated list of sales recorded by employees.
    Only admins can access this endpoint.
    """
    admin_id = admin.get("admin_id")
    if not admin_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Start with an empty query to fetch all sales
    query = {}

    # Apply Employee ID filter if provided
    if employee_id:
        try:
            query["employee_id"] = ObjectId(employee_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid Employee ID format")

    # Apply Date Range filter
    date_filter = {}
    if start_date:
        try:
            date_filter["$gte"] = datetime.strptime(start_date, "%Y-%m-%d")
        except:
            raise HTTPException(status_code=400, detail="Invalid start date format. Use YYYY-MM-DD.")
    if end_date:
        try:
            date_filter["$lte"] = datetime.strptime(end_date, "%Y-%m-%d")
        except:
            raise HTTPException(status_code=400, detail="Invalid end date format. Use YYYY-MM-DD.")

    if date_filter:
        query["sale_date"] = date_filter

    # Pagination logic
    skip = (page - 1) * page_size
    total_sales = await sales_collection.count_documents(query)

    # Fetch paginated sales
    sales_cursor = sales_collection.find(query).skip(skip).limit(page_size)
    sales = await sales_cursor.to_list(length=page_size)

    # Convert ObjectId fields to strings
    for sale in sales:
        sale["_id"] = str(sale["_id"])
        sale["employee_id"] = str(sale["employee_id"])

    return {
        "sales": sales,
        "total_sales": total_sales,
        "page": page,
        "page_size": page_size,
        "total_pages": (total_sales + page_size - 1) // page_size,  # Round up
    }      
    