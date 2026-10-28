# import os
# import cv2
# from pdf2image import convert_from_path
# from paddleocr import PaddleOCR
# from typing import List, Tuple


# # ----------------------------
# # STEP 1: PDF → Images
# # ----------------------------
# def pdf_to_images(pdf_path: str, output_folder: str = "data/images") -> List[str]:
#     """
#     Converts each page of PDF into images and saves them.

#     Args:
#         pdf_path (str): Path to PDF file.
#         output_folder (str): Directory where images will be saved.

#     Returns:
#         List[str]: List of saved image file paths.
#     """
#     if not os.path.exists(output_folder):
#         os.makedirs(output_folder)

#     pages = convert_from_path(pdf_path, dpi=300)  # high resolution for OCR
#     image_paths = []

#     for i, page in enumerate(pages):
#         img_path = os.path.join(output_folder, f"page_{i+1}.png")
#         page.save(img_path, "PNG")
#         image_paths.append(img_path)

#     return image_paths


# # ----------------------------
# # STEP 2: Image Preprocessing
# # ----------------------------
# def preprocess_image(img_path: str) -> str:
#     """
#     Preprocess image for better OCR accuracy (without rotation/deskewing).

#     Args:
#         img_path (str): Path to input image.

#     Returns:
#         str: Path to preprocessed image.
#     """
#     image = cv2.imread(img_path, cv2.IMREAD_COLOR)

#     # Convert to grayscale
#     gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

#     # Denoising
#     denoised = cv2.fastNlMeansDenoising(gray, h=30)

#     # Thresholding (binarization)
#     _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

#     # Save preprocessed image (no rotation applied)
#     processed_path = img_path.replace(".png", "_processed.png")
#     cv2.imwrite(processed_path, thresh)

#     return processed_path



# # ----------------------------
# # STEP 3: Run PaddleOCR
# # ----------------------------
# def run_ocr(image_path: str) -> List[Tuple[str, float]]:
#     """
#     Run OCR on an image using PaddleOCR.

#     Args:
#         image_path (str): Path to image.

#     Returns:
#         List[Tuple[str, float]]: Extracted text with confidence scores.
#     """
#     ocr = PaddleOCR(use_textline_orientation=True, lang='en')
#     results = ocr.predict(image_path)
#     print(f"results: {results}")

#     extracted = []
#     if isinstance(results, list) and "rec_texts" in results[0]:
#         # PaddleX style result (dict format)
#         rec_texts = results[0]["rec_texts"]
#         rec_scores = results[0]["rec_scores"]

#         for text, score in zip(rec_texts, rec_scores):
#             extracted.append((text, score))

#     else:
#         # Standard PaddleOCR style
#         for line in results[0]:
#             box = line[0]
#             if isinstance(line[1], tuple):
#                 text, confidence = line[1]
#             else:  # fallback if it's just a string
#                 text, confidence = line[1], None
#             extracted.append((text, confidence))

#     return extracted

# # ----------------------------
# # MAIN PIPELINE
# # ----------------------------
# def extract_text_from_pdf(pdf_path: str):
#     """
#     Full pipeline: PDF → Images → Preprocess → OCR → Text
#     """
#     image_paths = pdf_to_images(pdf_path)

#     all_text = []
#     for img_path in image_paths:
#         processed_img = preprocess_image(img_path)
#         text_data = run_ocr(processed_img)
#         all_text.extend(text_data)

#     return all_text


# if __name__ == "__main__":
#     pdf_file = "data/46500152___20240912_060559-redacted.pdf"
#     extracted_text = extract_text_from_pdf(pdf_file)

#     print("\n--- Extracted Text ---")
#     for text, conf in extracted_text:
#         print(f"Text: {text}, Confidence: {conf}")


import os
import re
import cv2
from pdf2image import convert_from_path
from paddleocr import PaddleOCR
from typing import List, Tuple
import json
import ollama
import openai
from typing import Optional
from langchain_ollama import OllamaLLM
from langchain.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
from functools import lru_cache
from src.common import ColumnExtraction, DataExtractionHandler, Extraction
from langchain.output_parsers import OutputFixingParser
from langchain_core.exceptions import OutputParserException
from google.api_core import exceptions as google_errors
from pdf2image import pdfinfo_from_path
from src.errors import TransientError
from src.logger_config import setup_logger

logger = setup_logger(__name__)
load_dotenv()

# Limits that keep one document from exhausting a pod's memory or time.
MAX_PAGES = int(os.getenv("MAX_PAGES", "30"))
OCR_DPI = int(os.getenv("OCR_DPI", "300"))
PDF_PAGE_TIMEOUT_SECONDS = int(os.getenv("PDF_PAGE_TIMEOUT_SECONDS", "120"))
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
# The Gemini client backs off and retries 429/5xx itself; past that the job is retried from the queue.
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))
TRANSIENT_LLM_ERRORS = (
    google_errors.TooManyRequests,  # also ResourceExhausted (quota)
    google_errors.ServerError,  # 5xx: InternalServerError, ServiceUnavailable, GatewayTimeout
    google_errors.DeadlineExceeded,
    google_errors.RetryError,
    ConnectionError,
    TimeoutError,
)


class ModelHandler:
    def __init__(self, model: str = "llama3.2:1b"):
        self.model = model
        logger.info(f"Initialized ModelHandler with model: {self.model}")

        # ✅ Setup parser for structured invoice extraction
        self.parser = PydanticOutputParser(pydantic_object=Extraction)

        # ✅ Setup common prompt
        self.prompt_template = PromptTemplate(
                template="""You are a strict JSON generator.
                - Output MUST be a single valid JSON object that conforms exactly to this schema:
                {format_instructions}
                - Do not include explanations, notes, bullet points, markdown, or text outside JSON.
                - If information is missing, set the value to null.
                - Return ONLY JSON.
                OCR Text: {ocr_text}
                """,
                input_variables=["ocr_text"],
                partial_variables={"format_instructions": self.parser.get_format_instructions()},
            )

        # Prompt for user-chosen columns, with a cited source line per value
        self.columns_parser = PydanticOutputParser(pydantic_object=ColumnExtraction)
        self.columns_template = PromptTemplate(
                template="""You extract specific columns from a document. You are a strict JSON generator.
                Columns to extract:
                {columns}
                The document text is given line by line as "[L<n>] (p<page>) <text>".
                - Return one row per distinct record: one per line item when the columns describe items,
                  or a single row when they describe the document as a whole.
                - Each row has one cell per requested column, using the column name exactly as given.
                - "value" is the value as written in the document, or null if it is not present. Never invent values.
                - "line" is the <n> of the line the value was read from, or null when value is null.
                - Output MUST be a single valid JSON object that conforms exactly to this schema:
                {format_instructions}
                - Return ONLY JSON.
                Document text:
                {ocr_text}
                """,
                input_variables=["ocr_text", "columns"],
                partial_variables={"format_instructions": self.columns_parser.get_format_instructions()},
            )

    def extract_with_llama(self, ocr_text: str) -> Optional[dict]:
        """Extracts structured data using Ollama (llama model) + Pydantic parser"""
        try:            
            llama_llm = OllamaLLM(model=self.model)
            
            chain = self.prompt_template | llama_llm | self.parser  # ensures parsing
            
            fixing_parser = OutputFixingParser.from_llm(
                parser=self.parser, llm=llama_llm
            )
            
            try:
                response = chain.invoke({"ocr_text": ocr_text})
                json_str = re.search(r"\{.*\}", response, re.DOTALL).group(0)  # get JSON only
                return json.loads(json_str)
                # fix_response = fixing_parser.parse(response)
                # return fix_response.dict()
            except Exception:
                # fallback: try parsing raw output
                raw_output = llama_llm.invoke(self.prompt_template.format(ocr_text=ocr_text))
                return self.parser.parse(raw_output).model_dump()
        except Exception as e:
            logger.error(f"Error during Llama extraction: {e}")
            return None
            # prompt = self.prompt_template.format_prompt(ocr_text=ocr_text).to_string()

            # logger.debug(f"Sending prompt to Llama: {prompt}")

            # response = ollama.chat(
            #     model="llama3.2:1b",
            #     messages=[{"role": "user", "content": prompt}]
            # )

            # raw_output = response["message"]["content"]
            # logger.debug(f"Llama raw output: {raw_output}")

            # # ✅ Parse into Pydantic Extraction object
            # return self.parser.parse(raw_output).dict()

    def extract_with_gemini(self, ocr_text: str, callbacks: Optional[list] = None) -> Optional[dict]:
        """Extracts structured data using Gemini models via LangChain + Pydantic parser.

        `callbacks` are LangChain callback handlers (token/cost metrics, Langfuse tracing).
        """
        return self._invoke_gemini(self.prompt_template, self.parser, {"ocr_text": ocr_text}, callbacks)

    def extract_columns(self, ocr_text: str, columns: List[str], callbacks: Optional[list] = None) -> Optional[dict]:
        """Extracts only the user's columns, citing the [L<n>] line each value came from.

        `ocr_text` must be line-numbered (src.sources.numbered_text).
        """
        inputs = {"ocr_text": ocr_text, "columns": "\n".join(f"- {c}" for c in columns)}
        return self._invoke_gemini(self.columns_template, self.columns_parser, inputs, callbacks)

    def _invoke_gemini(self, template: PromptTemplate, parser: PydanticOutputParser, inputs: dict,
                       callbacks: Optional[list] = None) -> Optional[dict]:
        """Raises TransientError when Gemini stays unavailable after the client's own retries.

        Prompts and responses hold customer documents, so only error types are logged.
        """
        config = {"callbacks": callbacks or []}
        try:
            gemini_llm = ChatGoogleGenerativeAI(model=self.model, timeout=LLM_TIMEOUT_SECONDS, max_retries=LLM_MAX_RETRIES)
            raw_output = (template | gemini_llm).invoke(inputs, config=config).content
            try:
                return parser.parse(raw_output).model_dump()
            except OutputParserException as e:
                # Ask the model to repair its own output rather than re-running the whole extraction.
                logger.warning(f"Parsing failed ({type(e).__name__}), attempting fixing parser")
                fixing_parser = OutputFixingParser.from_llm(parser=parser, llm=gemini_llm)
                return fixing_parser.parse(raw_output).model_dump()
        except TRANSIENT_LLM_ERRORS as e:
            raise TransientError(f"Gemini unavailable: {type(e).__name__}: {e}") from e
        except Exception as e:
            logger.error(f"Error during Gemini extraction: {type(e).__name__}")
            return None

            # raw_output = response.content.strip()
            # logger.debug(f"Gemini raw output: {raw_output}")

            # return self.parser.parse(raw_output).model_dump()
        # except Exception as e:
        #     logger.error(f"Error during Gemini extraction: {e}")
        #     return None
        
def process_extracted_texts(input_folder: str = "output", save_folder: str = "structured_output"):
    """
    Reads all OCR text files from `output/`, extracts structured data, and saves JSON.
    """
    os.makedirs(save_folder, exist_ok=True)

    model_handler = ModelHandler("gemini-2.5-flash")
    handler = DataExtractionHandler()

    for root, _, files in os.walk(input_folder):
        for file in files:
            if file.endswith(".txt"):
                txt_path = os.path.join(root, file)

                logger.info(f"Processing OCR text file: {txt_path}")
                with open(txt_path, "r", encoding="utf-8") as f:
                    ocr_text = f.read()

                # Run with Llama
                llama_result = model_handler.extract_with_gemini(ocr_text = ocr_text)

                if llama_result:
                    logger.info("Structured Data extracted from Llama")
                    logger.info(f"{json.dumps(llama_result, indent=4)}")

                    # Validate + Save JSON per file
                    validated = handler.validate_data(llama_result)

                    pdf_name = os.path.splitext(file)[0]
                    save_path = os.path.join(save_folder, f"{pdf_name}.json")
                    handler.save_json_to_file(validated, save_path)

                    logger.info(f"Saved structured JSON to {save_path}")
                else:
                    logger.error(f"Failed to extract data for {file}")

# ----------------------------
# STEP 1: PDF → Images
# ----------------------------
def pdf_to_images(pdf_path: str, output_root: str = "output") -> List[str]:
    """
    Converts each page of PDF into images and saves them in output folder.

    Args:
        pdf_path (str): Path to PDF file.
        output_root (str): Root directory where images/text will be saved.

    Returns:
        List[str]: List of saved image file paths.
    """
    page_count = pdfinfo_from_path(pdf_path, timeout=PDF_PAGE_TIMEOUT_SECONDS)["Pages"]
    if MAX_PAGES and page_count > MAX_PAGES:
        raise ValueError(f"Document has {page_count} pages; the limit is {MAX_PAGES}")

    pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
    pdf_output_folder = os.path.join(output_root, pdf_name, "images")
    os.makedirs(pdf_output_folder, exist_ok=True)

    image_paths = []
    for i in range(1, page_count + 1):
        # One page at a time: rendering the whole PDF at once holds every page in memory.
        page = convert_from_path(
            pdf_path, dpi=OCR_DPI, first_page=i, last_page=i, timeout=PDF_PAGE_TIMEOUT_SECONDS
        )[0]
        img_path = os.path.join(pdf_output_folder, f"page_{i}.png")
        page.save(img_path, "PNG")
        page.close()
        image_paths.append(img_path)

    return image_paths


# ----------------------------
# STEP 2: Image Preprocessing
# ----------------------------
def preprocess_image(img_path: str) -> str:
    """
    Preprocess image for better OCR accuracy (without rotation/deskewing).

    Args:
        img_path (str): Path to input image.

    Returns:
        str: Path to preprocessed image.
    """
    image = cv2.imread(img_path, cv2.IMREAD_COLOR)

    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Denoising
    denoised = cv2.fastNlMeansDenoising(gray, h=30)

    # Thresholding (binarization)
    _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Save preprocessed image
    processed_path = img_path.replace(".png", "_processed.png")
    cv2.imwrite(processed_path, thresh)

    return processed_path


def image_to_png(image_path: str, output_root: str = "output") -> str:
    """Copy an uploaded image (jpg, tiff, ...) to a PNG page so it runs through the same OCR steps as PDF pages."""
    image = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not read image {os.path.basename(image_path)}")
    name = os.path.splitext(os.path.basename(image_path))[0]
    folder = os.path.join(output_root, name, "images")
    os.makedirs(folder, exist_ok=True)
    png_path = os.path.join(folder, "page_1.png")
    cv2.imwrite(png_path, image)
    return png_path


# ----------------------------
# STEP 3: Run PaddleOCR
# ----------------------------
@lru_cache(maxsize=1)
def _ocr_engine() -> PaddleOCR:
    # Loading the models takes seconds; build once per process instead of once per page.
    return PaddleOCR(use_textline_orientation=True, lang='en')


def run_ocr(image_path: str) -> List[Tuple[str, float]]:
    """
    Run OCR on an image using PaddleOCR.

    Args:
        image_path (str): Path to image.

    Returns:
        List[Tuple[str, float]]: Extracted text with confidence scores.
    """
    results = _ocr_engine().predict(image_path)

    extracted = []
    if isinstance(results, list) and "rec_texts" in results[0]:
        rec_texts = results[0]["rec_texts"]
        rec_scores = results[0]["rec_scores"]

        for text, score in zip(rec_texts, rec_scores):
            extracted.append((text, score))
    else:
        for line in results[0]:
            if isinstance(line[1], tuple):
                text, confidence = line[1]
            else:
                text, confidence = line[1], None
            extracted.append((text, confidence))

    return extracted


# ----------------------------
# MAIN PIPELINE
# ----------------------------
def extract_text_from_pdf(pdf_path: str, output_root: str = "output"):
    """
    Full pipeline: PDF → Images → Preprocess → OCR → Text
    """
    pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
    text_output_path = os.path.join(output_root, pdf_name, f"{pdf_name}.txt")
    os.makedirs(os.path.dirname(text_output_path), exist_ok=True)

    image_paths = pdf_to_images(pdf_path, output_root)
    all_text = []

    for img_path in image_paths:
        processed_img = preprocess_image(img_path)
        text_data = run_ocr(processed_img)
        all_text.extend(text_data)

    # Save extracted text
    with open(text_output_path, "w", encoding="utf-8") as f:
        for text, conf in all_text:
            f.write(f"{text} (conf: {conf})\n")

    return all_text


def ocr_pages(path: str, output_root: str = "output") -> List[List[Tuple[str, float]]]:
    """PDF or image → OCR lines for each page, so values can be traced back to their page."""
    if path.lower().endswith(".pdf"):
        image_paths = pdf_to_images(path, output_root)
    else:
        image_paths = [image_to_png(path, output_root)]
    return [run_ocr(preprocess_image(img_path)) for img_path in image_paths]


if __name__ == "__main__":
    # pdf_folder = "data"
    # pdf_files = [f for f in os.listdir(pdf_folder) if f.lower().endswith(".pdf")]

    # for pdf_file in pdf_files:
    #     pdf_path = os.path.join(pdf_folder, pdf_file)
    #     logger.info(f"\n=== Processing {pdf_file} ===")
    #     extracted_text = extract_text_from_pdf(pdf_path, output_root="output")

    #     logger.info(f"Saved results in output/{os.path.splitext(pdf_file)[0]}/")
        
    process_extracted_texts()
