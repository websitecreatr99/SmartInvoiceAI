"""Runs worker.py with FakeGemini in place of Gemini (end-to-end tests without an API key).

    docker run -v $PWD/tests/e2e:/e2e:ro ... invoiceai-worker python /e2e/run_worker.py
"""
import os
import runpy
import sys

sys.path[:0] = ["/app", os.path.dirname(os.path.abspath(__file__))]

import ocr_pipeline  # noqa: E402
from fake_gemini import FakeGemini  # noqa: E402

ocr_pipeline.ChatGoogleGenerativeAI = FakeGemini
runpy.run_path(os.path.join(sys.path[0], "worker.py"), run_name="__main__")
