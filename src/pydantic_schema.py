from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional

# Define the Pydantic models with Field descriptions and default values set to None

class Address(BaseModel):
    name: Optional[str] = Field(default=None, description="Name associated with the address")
    address1: Optional[str] = Field(default=None, description="Primary address line")
    address2: Optional[str] = Field(default=None, description="Secondary address line")
    address3: Optional[str] = Field(default=None, description="Tertiary address line (if applicable)")
    city: Optional[str] = Field(default=None, description="City name")
    state: Optional[str] = Field(default=None, description="State or region")
    country: Optional[str] = Field(default=None, description="Country name")
    country_code: Optional[str] = Field(default=None, description="ISO country code")
    zip: Optional[str] = Field(default=None, description="Postal/ZIP code")

class Contact(BaseModel):
    name: Optional[str] = Field(default=None, description="Contact's full name")
    email: Optional[str] = Field(default=None, description="Contact's email address")
    contact_number: Optional[str] = Field(default=None, description="Contact's phone number")

class Header(BaseModel):
    ship_to: Optional[Address] = Field(default=None, description="Shipping address details")
    bill_to: Optional[Address] = Field(default=None, description="Billing address details")
    vendor: Optional[Address] = Field(default=None, description="Vendor details")
    buyer_contact: Optional[Contact] = Field(default=None, description="Contact details for the buyer")
    shipping_contact: Optional[Contact] = Field(default=None, description="Contact details for shipping")
    # project_number: Optional[str] = Field(default=None, description="Unique project identifier")
    # purchase_order_number: Optional[str] = Field(default=None, description="Purchase order reference")
    # job_name: Optional[str] = Field(default=None, description="Name of the job associated with the order")
    # job_number: Optional[str] = Field(default=None, description="Unique identifier for the job")
    # quote_number: Optional[str] = Field(default=None, description="Quote reference number")
    # date_ordered: Optional[str] = Field(default=None, description="Date the order was placed")
    # delivery_date: Optional[str] = Field(default=None, description="Expected delivery date")
    # shipping_instructions: Optional[str] = Field(default=None, description="Special shipping instructions")
    # notes: Optional[str] = Field(default=None, description="Additional notes for the order")
    # ship_via: Optional[str] = Field(default=None, description="Shipping method")
    # payment_terms: Optional[str] = Field(default=None, description="Payment terms for the order")

# class LineItem(BaseModel):
#     line_no: Optional[str] = Field(default=None, description="Line item number")
#     on_hand: Optional[str] = Field(default=None, description="Quantity on hand")
#     to_buy: Optional[str] = Field(default=None, description="Quantity to be purchased")
#     quantity: Optional[int] = Field(default=None, description="Total quantity of the item")
#     uom: Optional[str] = Field(default=None, description="Unit of measure (e.g., PCS, KG)")
#     unit_price: Optional[str] = Field(default=None, description="Price per unit")
#     currency: Optional[str] = Field(default=None, description="Currency of the unit price")
#     part_numbers: Optional[str] = Field(default=None, description="Part number for the item")
#     product_description: Optional[str] = Field(default=None, description="Description of the product")
#     spell_corrected_product_description: Optional[str] = Field(default=None, description="Corrected product description (if applicable)")

class ExtractionItem(BaseModel):
    header: Optional[Header] = Field(default=None, description="Metadata and general order information")
    # line_items: Optional[List[LineItem]] = Field(default=None, description="List of items included in the order")

class Extraction(BaseModel):
    extraction: List[ExtractionItem] = Field(..., description="List of extracted orders")
    
# Example function to validate data
def validate_data(input_data: dict):
    try:
        # Parse and validate data
        validated_data = Extraction(**input_data)
        print("Validation successful!")
        return validated_data
    except ValidationError as e:
        # Handle validation errors
        print("Validation failed:")
        for error in e.errors():
            print(f"Field: {error['loc']}, Error: {error['msg']}, Type: {error['type']}")
        raise e  # Optionally re-raise the exception for further handling
