from .logger_config import setup_logger
from pydantic import BaseModel, Field, ValidationError, field_validator
from typing import List, Optional

logger = setup_logger(__name__)
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
    project_number: Optional[str] = Field(default=None, description="Unique project identifier")
    purchase_order_number: Optional[str] = Field(default=None, description="Purchase order reference")
    job_name: Optional[str] = Field(default=None, description="Name of the job associated with the order")
    job_number: Optional[str] = Field(default=None, description="Unique identifier for the job")
    quote_number: Optional[str] = Field(default=None, description="Quote reference number")
    date_ordered: Optional[str] = Field(default=None, description="Date the order was placed")
    delivery_date: Optional[str] = Field(default=None, description="Expected delivery date")
    shipping_instructions: Optional[str] = Field(default=None, description="Special shipping instructions")
    notes: Optional[str] = Field(default=None, description="Additional notes for the order")
    ship_via: Optional[str] = Field(default=None, description="Shipping method")
    payment_terms: Optional[str] = Field(default=None, description="Payment terms for the order")

class LineItem(BaseModel):
    line_no: Optional[str] = Field(default=None, description="Line item number")
    on_hand: Optional[str] = Field(default=None, description="Quantity on hand")
    to_buy: Optional[str] = Field(default=None, description="Quantity to be purchased")
    quantity: Optional[int] = Field(default=None, description="Total quantity of the item")
    uom: Optional[str] = Field(default=None, description="Unit of measure (e.g., PCS, KG)")
    unit_price: Optional[str] = Field(default=None, description="Price per unit")
    currency: Optional[str] = Field(default=None, description="Currency of the unit price")
    part_numbers: Optional[str] = Field(default=None, description="Part number for the item")
    product_description: Optional[str] = Field(default=None, description="Description of the product")
    spell_corrected_product_description: Optional[str] = Field(default=None, description="Corrected product description (if applicable)")

class ExtractionItem(BaseModel):
    header: Optional[Header] = Field(default=None, description="Metadata and general order information")
    line_items: Optional[List[LineItem]] = Field(default=None, description="List of items included in the order")

class Extraction(BaseModel):
    extraction: List[ExtractionItem] = Field(..., description="List of extracted orders")


# Used instead of Extraction when the user names the columns they want.

class Cell(BaseModel):
    column: str = Field(..., description="Column name, exactly as requested")
    value: Optional[str] = Field(default=None, description="Value as written in the document, or null if absent")
    line: Optional[int] = Field(default=None, description="The <n> of the [L<n>] line the value was read from")

    @field_validator("value", mode="before")
    @classmethod
    def stringify(cls, v):
        return None if v is None else str(v)


class Row(BaseModel):
    cells: List[Cell] = Field(..., description="One cell per requested column")


class ColumnExtraction(BaseModel):
    rows: List[Row] = Field(..., description="One row per record found in the document")


def describe_validation_error(e: ValidationError) -> str:
    """Field paths and reasons only: pydantic's default message echoes the (customer) input values."""
    return "; ".join(
        f"{'.'.join(str(part) for part in err['loc']) or 'root'}: {err['msg']}"
        for err in e.errors(include_input=False, include_url=False)
    )


class DataExtractionHandler:

    def validate_data(self, data: dict) -> str:
        """
        Validates and parses input data into JSON format based on the defined schema.

        Args:
            data (dict): Input data to be validated and parsed.

        Returns:
            str: Validated data in JSON format or error message in case of validation failure.
        """
        logger.debug("Validating extracted data against the schema.")
        try:
            parsed_data = Extraction(**data)
            logger.info("Data validation successful.")
            return parsed_data.model_dump_json(indent=4)
        except ValidationError as e:
            message = f"Validation Error: {describe_validation_error(e)}"
            logger.error(message)
            return message

    def save_json_to_file(self, json_data: str, filename: str):
        """
        Saves the JSON data to a file.

        Args:
            json_data (str): JSON string to save.
            filename (str): Name of the file to save the JSON data.
        """
        logger.debug(f"Saving JSON data to file: {filename}")
        try:
            # Explicit UTF-8: the Windows default (cp1252) breaks readers on characters like "·".
            with open(filename, 'w', encoding='utf-8') as file:
                file.write(json_data)
            logger.info(f"JSON data successfully saved to {filename}")
        except Exception as e:
            logger.error(f"Error saving JSON data to file: {e}")