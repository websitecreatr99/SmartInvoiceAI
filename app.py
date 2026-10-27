# # import json
# # from typing import List, Optional
# # from pydantic import BaseModel, Field, ValidationError
# # import openai  # Placeholder for GPT-4 integration
# # from src.common import DataExtractionHandler
# # import ollama
# # from src.logger import logging
# # import logging
# # import json
# # from typing import Optional
# # import openai
# # import ollama
# # from langchain_google_genai import ChatGoogleGenerativeAI
# # from langchain_core.prompts import ChatPromptTemplate
# # from dotenv import load_dotenv

# # load_dotenv()   # this loads GOOGLE_API_KEY into environment

# # class ModelHandler:
# #     def __init__(self, model: str = "gpt-4", gemini_model: str = "gemini-1.5-pro", api_key: Optional[str] = None):
# #         self.model = model
# #         self.gemini_model = gemini_model
# #         self.api_key = api_key
# #         logging.info(f"Initialized ModelHandler with GPT model: {self.model} and Gemini model: {self.gemini_model}")

# #         # Initialize Gemini LLM once
# #         self.gemini_llm = ChatGoogleGenerativeAI(
# #             model=self.gemini_model
# #         )

# #     def extract_with_gpt4(self, prompt: str) -> Optional[dict]:
# #         """Extracts data using GPT-4 models based on the provided prompt."""
# #         logging.debug(f"Sending prompt to {self.model}: {prompt}")
# #         try:
# #             response = openai.ChatCompletion.create(
# #                 model=self.model,
# #                 messages=[
# #                     {"role": "system", "content": "You are a data extraction assistant."},
# #                     {"role": "user", "content": prompt}
# #                 ]
# #             )
# #             logging.info("Data successfully extracted from GPT-4.")
# #             return json.loads(response["choices"][0]["message"]["content"])
# #         except Exception as e:
# #             logging.error(f"Error during GPT-4 extraction: {e}")
# #             return None

# #     def extract_with_llama(self, prompt: str) -> Optional[dict]:
# #         """Extracts data using llama3.2:1b models based on the provided prompt."""
# #         try:
# #             logging.debug(f"Sending prompt to llama3.2:1b: {prompt}")
# #             stream = ollama.chat(
# #                 model="llama3.2:1b",
# #                 messages=[{"role": "user", "content": prompt}],
# #                 stream=True
# #             )
# #             logging.info("Data successfully extracted from llama3.2:1b.")
# #             for chunk in stream:
# #                 print(chunk["message"]["content"], end="", flush=True)
# #         except Exception as e:
# #             logging.error(f"Error during LLAMA3.1 extraction: {e}")
# #             return None

# #     def extract_with_gemini(self, prompt: str) -> Optional[dict]:
# #         """Extracts structured data using Gemini models via LangChain."""
# #         logging.debug(f"Sending prompt to {self.gemini_model}: {prompt}")
# #         try:
# #             template = ChatPromptTemplate.from_messages([
# #                 ("system", "You are a data extraction assistant. Always return valid JSON."),
# #                 ("user", "{input}")
# #             ])
# #             chain = template | self.gemini_llm

# #             response = chain.invoke({"input": prompt})

# #             content = response.content.strip()
# #             logging.info("Data successfully extracted from Gemini.")

# #             return json.loads(content)  # Expect JSON
# #         except Exception as e:
# #             logging.error(f"Error during Gemini extraction: {e}")
# #             return None

# # # # Define the main extraction handler class
# # # class ModelHandler:
# # #     def __init__(self, model: str = "gpt-4"):
# # #         self.model = model
# # #         logging.info(f"Initialized DataExtractionHandler with model: {self.model}")

# # #     def extract_with_gpt4(self, prompt: str) -> Optional[dict]:
# # #         """
# # #         Extracts data using GPT-4 models based on the provided prompt.

# # #         Args:
# # #             prompt (str): The input prompt.

# # #         Returns:
# # #             dict: Extracted data or None if the model fails to extract.
# # #         """
# # #         logging.debug(f"Sending prompt to {self.model}: {prompt}")
# # #         try:
# # #             # Replace with actual GPT-4 API call
# # #             response = openai.ChatCompletion.create(
# # #                 model=self.model,
# # #                 messages=[
# # #                     {"role": "system", "content": "You are a data extraction assistant."},
# # #                     {"role": "user", "content": prompt}
# # #                 ]
# # #             )
# # #             logging.info("Data successfully extracted from GPT-4.")
# # #             return json.loads(response["choices"][0]["message"]["content"])
# # #         except Exception as e:
# # #             logging.error(f"Error during GPT-4 extraction: {e}")
# # #             return None
        
# # #     def extract_with_llama(self, prompt: str) -> Optional[dict]:
# # #         """
# # #             Extracts data using LLAMA3.1 models based on the provided prompt.

# # #             Args:
# # #                 prompt (str): The input prompt.

# # #             Returns:
# # #                 dict: Extracted data or None if the model fails to extract.
# # #         """
# # #         try:
# # #             logging.debug(f"Sending prompt to {self.model}: {prompt}")
# # #             stream = ollama.chat(
# # #             model='llama3.1',
# # #             messages=[{'role': 'user', 'content': 'You are a data extraction assistant.'}],
# # #             stream=True
# # #             ) 
# # #             logging.info("Data successfully extracted from LLAMA3.1")
# # #             for chunk in stream:
# # #                 print(chunk['message']['content'], end='', flush=True)
# # #         except Exception as e:
# # #             logging.error(f"Error during LLAMA3.1 extraction: {e}")
# # #             return None
        
# # #     def extract_with_gemini(self, prompt: str) -> Optional[dict]:
# # #         """
# # #         Extracts structured data using Gemini models via LangChain.

# # #         Args:
# # #             prompt (str): The input prompt.

# # #         Returns:
# # #             dict: Extracted data or None if the model fails.
# # #         """
# # #         logging.debug(f"Sending prompt to {self.model_name}: {prompt}")
# # #         try:
# # #             # Define system + user roles like in GPT-4
# # #             template = ChatPromptTemplate.from_messages([
# # #                 ("system", "You are a data extraction assistant. Always return valid JSON."),
# # #                 ("user", "{input}")
# # #             ])
# # #             chain = template | self.llm

# # #             # Run chain
# # #             response = chain.invoke({"input": prompt})

# # #             # LangChain responses keep the text in .content
# # #             content = response.content.strip()
# # #             logging.info("Data successfully extracted from Gemini.")

# # #             return json.loads(content)  # Expect JSON output
# # #         except Exception as e:
# # #             logging.error(f"Error during Gemini extraction: {e}")
# # #             return None

# # # Example usage
# # if __name__ == "__main__":
# #     model_handler = ModelHandler(
# #             model="gpt-4",                # GPT model
# #             gemini_model="gemini-1.5-pro",# Gemini model
# #             # api_key="YOUR_GOOGLE_API_KEY" # Required for Gemini
# #         )
# #     handler = DataExtractionHandler()

# #     # Generate prompt for GPT-4
# #     prompt_template = PromptTemplate(
# #             template="""
# #         Extract invoice details from the OCR text.

# #         OCR Text:
# #         {ocr_text}

# #         {format_instructions}
# #         """,
# #             input_variables=["ocr_text"],
# #             partial_variables={"format_instructions": parser.get_format_instructions()},
# #         )
# #     # gpt4_result = model_handler.extract_with_gpt4(prompt)
# #     gemini_result = model_handler.extract_with_llama(prompt_template)

# #     if gemini_result:
# #         logging.debug("Gemini Extraction Result:")
# #         logging.debug(gemini_result)

# #         # Validate and save the result
# #         validation_result = handler.validate_data(gemini_result)
# #         logging.debug(validation_result)

# #         # Save validated JSON
# #         handler.save_json_to_file(validation_result, "output.json")
# #     else:
# #         logging.error("Failed to extract data.")



# import os
# import json
# import ollama
# import openai
# from typing import Optional
# from langchain_community.llms import Ollama
# from langchain.prompts import PromptTemplate
# from langchain.output_parsers import PydanticOutputParser
# from langchain_google_genai import ChatGoogleGenerativeAI
# from dotenv import load_dotenv
# from src.common import DataExtractionHandler, Extraction
# from src.logger_config import logging

# load_dotenv()


# class ModelHandler:
#     def __init__(self, model: str = "gpt-4", gemini_model: str = "gemini-1.5-pro", api_key: Optional[str] = None):
#         self.model = model
#         self.gemini_model = gemini_model
#         self.api_key = api_key
#         logging.info(f"Initialized ModelHandler with GPT model: {self.model} and Gemini model: {self.gemini_model}")

#         # Initialize Gemini LLM once
#         self.gemini_llm = ChatGoogleGenerativeAI(
#             model=self.gemini_model
#         )

#         # ✅ Setup parser for structured invoice extraction
#         self.parser = PydanticOutputParser(pydantic_object=Extraction)

#         # ✅ Setup common prompt
#         self.prompt_template = PromptTemplate(
#             template="""
#             Extract structured invoice details from the OCR text.
            
#             OCR Text:
#             {ocr_text}
            
#             {format_instructions}
#             """,
#             input_variables=["ocr_text"],
#             partial_variables={"format_instructions": self.parser.get_format_instructions()},
#         )

#     def extract_with_llama(self, ocr_text: str) -> Optional[dict]:
#         """Extracts structured data using Ollama (llama model) + Pydantic parser"""
#         try:
#             parser = PydanticOutputParser(pydantic_object=Extraction)
            
#             llama_llm = Ollama(model="llama3.2:1b")

#             prompt_template = PromptTemplate(
#                             template="""
#                 You are a data extraction assistant. 
#                 Extract invoice/order details from the OCR text and return ONLY valid JSON matching this schema:

#                 {format_instructions}

#                 OCR Text:
#                 {ocr_text}
#                 """,
#             input_variables=["ocr_text"],
#             partial_variables={"format_instructions": parser.get_format_instructions()},
#             )

#             chain = prompt_template | llama_llm | parser  # ensures parsing
#             response = chain.invoke({"ocr_text": ocr_text})

#             return response.dict()  # already validated
        
#             # prompt = self.prompt_template.format_prompt(ocr_text=ocr_text).to_string()

#             # logging.debug(f"Sending prompt to Llama: {prompt}")

#             # response = ollama.chat(
#             #     model="llama3.2:1b",
#             #     messages=[{"role": "user", "content": prompt}]
#             # )

#             # raw_output = response["message"]["content"]
#             # logging.debug(f"Llama raw output: {raw_output}")

#             # # ✅ Parse into Pydantic Extraction object
#             # return self.parser.parse(raw_output).dict()
#         except Exception as e:
#             logging.error(f"Error during Llama extraction: {e}")
#             return None

#     def extract_with_gemini(self, ocr_text: str) -> Optional[dict]:
#         """Extracts structured data using Gemini models via LangChain + Pydantic parser"""
#         try:
#             prompt = self.prompt_template.format_prompt(ocr_text=ocr_text)
#             response = self.gemini_llm.invoke(prompt)

#             raw_output = response.content.strip()
#             logging.debug(f"Gemini raw output: {raw_output}")

#             return self.parser.parse(raw_output).dict()
#         except Exception as e:
#             logging.error(f"Error during Gemini extraction: {e}")
#             return None
        
# def process_extracted_texts(input_folder: str = "output", save_folder: str = "structured_output"):
#     """
#     Reads all OCR text files from `output/`, extracts structured data, and saves JSON.
#     """
#     os.makedirs(save_folder, exist_ok=True)

#     model_handler = ModelHandler()
#     handler = DataExtractionHandler()

#     for root, _, files in os.walk(input_folder):
#         for file in files:
#             if file.endswith(".txt"):
#                 txt_path = os.path.join(root, file)

#                 logging.info(f"Processing OCR text file: {txt_path}")
#                 with open(txt_path, "r", encoding="utf-8") as f:
#                     ocr_text = f.read()

#                 # Run with Llama
#                 llama_result = model_handler.extract_with_llama(ocr_text)

#                 if llama_result:
#                     logging.info("✅ Structured Data extracted from Llama")
#                     print(json.dumps(llama_result, indent=4))

#                     # Validate + Save JSON per file
#                     validated = handler.validate_data(llama_result)

#                     pdf_name = os.path.splitext(file)[0]
#                     save_path = os.path.join(save_folder, f"{pdf_name}.json")
#                     handler.save_json_to_file(validated, save_path)

#                     logging.info(f"Saved structured JSON to {save_path}")
#                 else:
#                     logging.error(f"❌ Failed to extract data for {file}")


# if __name__ == "__main__":
#     process_extracted_texts()


# # if __name__ == "__main__":
# #     ocr_text = """
# #        """

# #     model_handler = ModelHandler()
# #     handler = DataExtractionHandler()

# #     # Run with Llama
# #     llama_result = model_handler.extract_with_llama(ocr_text)

# #     if llama_result:
# #         logging.info("Structured Data from Llama:")
# #         print(json.dumps(llama_result, indent=4))

# #         # Validate + Save
# #         validated = handler.validate_data(llama_result)
# #         handler.save_json_to_file(validated, "invoice_output.json")
# #     else:
# #         logging.error("Failed to extract data with Llama")

from flask import Flask, render_template, request, jsonify
import os
import subprocess
import json

UPLOAD_FOLDER = "data"
STRUCTURED_OUTPUT_FOLDER = "structured_output"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STRUCTURED_OUTPUT_FOLDER, exist_ok=True)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload_files():
    """Save uploaded PDFs into data/ folder"""
    uploaded_files = request.files.getlist("pdfs")
    saved_files = []

    for file in uploaded_files:
        filename = file.filename
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(save_path)
        saved_files.append(filename)

    return jsonify({"success": True, "uploaded": saved_files})


@app.route("/delete", methods=["POST"])
def delete_file():
    """Delete a PDF before processing if user cancels"""
    data = request.get_json()
    filename = data.get("filename")
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

    if os.path.exists(file_path):
        os.remove(file_path)
        return jsonify({"success": True, "deleted": filename})
    else:
        return jsonify({"success": False, "error": "File not found"}), 404


@app.route("/process", methods=["POST"])
def process_files():
    """Run OCR pipeline on all uploaded PDFs and return structured JSONs"""
    results = []

    # 1️⃣ Run OCR pipeline if needed
    try:
        subprocess.run(["python", "ocr_pipeline.py"], check=True)
    except subprocess.CalledProcessError as e:
        return jsonify({"success": False, "error": f"OCR pipeline failed: {str(e)}"})

    # 2️⃣ Collect structured outputs
    for filename in os.listdir(STRUCTURED_OUTPUT_FOLDER):
        if filename.endswith(".json"):
            file_path = os.path.join(STRUCTURED_OUTPUT_FOLDER, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                results.append({"filename": filename, "structured_data": data})
            except Exception as e:
                results.append({"filename": filename, "error": str(e)})

    return jsonify({"success": True, "results": results})


if __name__ == "__main__":
    app.run(debug=True)


# pipreqs . --force


# pydantic
# openai
# ollama
# ipykernel
# langchain
# langchain_community
# unstructured
# PyPDF2
# google-cloud-vision==3.1.1 
# langchain-chroma>=0.1.2
# langchain-google-genai
# langchain-core
# python-dotenv
# paddleocr 
# paddlepaddle 
# pdf2image 
# opencv-python 
# pillow
# flask
# -e .
