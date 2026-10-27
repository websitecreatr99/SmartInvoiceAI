// Mirrors the Pydantic models in src/common.py.

export interface Address {
  name: string | null;
  address1: string | null;
  address2: string | null;
  address3: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  country_code: string | null;
  zip: string | null;
}

export interface Contact {
  name: string | null;
  email: string | null;
  contact_number: string | null;
}

export interface Header {
  ship_to: Address | null;
  bill_to: Address | null;
  vendor: Address | null;
  buyer_contact: Contact | null;
  shipping_contact: Contact | null;
  project_number: string | null;
  purchase_order_number: string | null;
  job_name: string | null;
  job_number: string | null;
  quote_number: string | null;
  date_ordered: string | null;
  delivery_date: string | null;
  shipping_instructions: string | null;
  notes: string | null;
  ship_via: string | null;
  payment_terms: string | null;
}

export interface LineItem {
  line_no: string | null;
  on_hand: string | null;
  to_buy: string | null;
  quantity: number | null;
  uom: string | null;
  unit_price: string | null;
  currency: string | null;
  part_numbers: string | null;
  product_description: string | null;
  spell_corrected_product_description: string | null;
}

export interface ExtractionItem {
  header: Header | null;
  line_items: LineItem[] | null;
}

export interface Extraction {
  extraction: ExtractionItem[];
}

export interface ResultItem {
  filename: string;
  structured_data?: Extraction | string;
  error?: string;
}

export type Stage = "idle" | "upload" | "ocr" | "ai" | "done" | "error";
