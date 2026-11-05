"""Offline regression: google-genai Client must outlive generate_content.

This test parses the function from app.py, so the test needs no Google Cloud
credentials, network requests, or third-party installed packages.
"""
import ast
import json
import pathlib
import unittest


SOURCE = pathlib.Path(__file__).resolve().parents[1] / "app.py"


class GeminiClientLifetimeTest(unittest.TestCase):
    def test_generate_content_is_inside_managed_client_scope(self):
        root = ast.parse(SOURCE.read_text(encoding="utf-8"))
        fn = next(
            n for n in root.body
            if isinstance(n, ast.FunctionDef) and n.name == "gemini_json"
        )
        with_nodes = [
            n for n in ast.walk(fn)
            if isinstance(n, ast.With)
            and any(
                isinstance(item.context_expr, ast.Call)
                and isinstance(item.context_expr.func, ast.Name)
                and item.context_expr.func.id == "gclient"
                and isinstance(item.optional_vars, ast.Name)
                and item.optional_vars.id == "client"
                for item in n.items
            )
        ]
        self.assertTrue(with_nodes, "Gemini client must have an explicit managed lifetime")
        has_request = any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "generate_content"
            and isinstance(n.func.value, ast.Attribute)
            and n.func.value.attr == "models"
            and isinstance(n.func.value.value, ast.Name)
            and n.func.value.value.id == "client"
            for scope in with_nodes for n in ast.walk(scope)
        )
        self.assertTrue(has_request, "generate_content must execute while client is open")


if __name__ == "__main__":
    unittest.main()
