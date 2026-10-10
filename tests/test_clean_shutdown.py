"""Regression: the process must be able to terminate after the retrieval models are loaded.

Root cause (found with a thread dump inside the Docker image): loading the S-PubMedBERT encoder from the Hub (a .bin-only repo) made
transformers start a NON-daemon `Thread-auto_conversion`; at shutdown Python waited for it forever, so the container stayed alive after
"Application shutdown complete" until Docker sent SIGKILL. src/retrieval/encoder.py now sets DISABLE_SAFETENSORS_CONVERSION=1.
"""
import os
import subprocess
import sys
import unittest

CODE = r"""
import os, sys, threading
sys.path.insert(0, os.path.abspath("."))
from src.retrieval.encoder import get_encoder
enc = get_encoder("primary")
enc.encode(["seizures"])
bad = [t.name for t in threading.enumerate() if t is not threading.main_thread() and not t.daemon]
print("NONDAEMON=" + repr(bad))
"""


class TestCleanShutdown(unittest.TestCase):
    def test_no_blocking_threads_and_process_exits(self):
        if not os.path.exists("data/vector_db/spubmedbert/disease.index"):
            self.skipTest("retrieval artifacts not provisioned")
        try:
            r = subprocess.run([sys.executable, "-W", "ignore", "-c", CODE], capture_output=True, text=True, timeout=240)
        except subprocess.TimeoutExpired:
            self.fail("process did not terminate by itself after loading the encoder (non-daemon thread still running)")
        if "Could not load embedding model" in (r.stderr or ""):
            self.skipTest("embedding model not available offline")
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        self.assertIn("NONDAEMON=[]", r.stdout)

    def test_conversion_switch_is_set(self):
        src = open("src/retrieval/encoder.py", encoding="utf-8").read()
        self.assertIn('os.environ.setdefault("DISABLE_SAFETENSORS_CONVERSION", "1")', src)
        self.assertIn("DISABLE_SAFETENSORS_CONVERSION=1", open("Dockerfile", encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
