"""Exercise chat request validation without initializing the live database."""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock

from flask import Flask, jsonify, request


class InventoryChatValidationTest(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path(__file__).with_name("app.py").read_text(encoding="utf-8"))
        handler = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                       and node.name == "inventory_chat_response")
        self.app = Flask(__name__)
        self.answer = Mock(return_value="answer")
        self.resolve = Mock(side_effect=lambda messages, question: question)
        namespace = dict(app=self.app, request=request, jsonify=jsonify,
                         answer_inventory_question=self.answer,
                         resolve_conversation_question=self.resolve)
        exec(compile(ast.Module(body=[handler], type_ignores=[]), "app.py", "exec"), namespace)
        self.app.add_url_rule("/chat", view_func=namespace["inventory_chat_response"], methods=["POST"])
        self.client = self.app.test_client()

    def test_short_questions_after_long_assistant_answer(self):
        for question in (
            "Cho tôi danh sách chương trình khuyến mãi đang áp dụng",
            "Mẫu nào đang được giảm nhiều nhất?",
            "Khuyến mãi nào sắp hết hạn?",
            "bạn là ai",
        ):
            with self.subTest(question=question):
                messages = [dict(role="user", content="Tồn kho"),
                            dict(role="assistant", content="x" * 5000),
                            dict(role="user", content=question)]
                response = self.client.post("/chat", json=dict(messages=messages))
                self.assertEqual(response.status_code, 200)
                self.answer.assert_called_with(question)
                self.resolve.assert_called_with(messages, question)

    def test_old_rejected_question_does_not_block_new_question(self):
        response = self.client.post("/chat", json=dict(messages=[
            dict(role="user", content="x" * 1001), dict(role="user", content="Giá 3DAO20")]))
        self.assertEqual(response.status_code, 200)

    def test_current_question_length_boundary(self):
        for length, status in ((1000, 200), (1001, 400)):
            with self.subTest(length=length):
                self.answer.reset_mock()
                response = self.client.post("/chat", json=dict(messages=[dict(role="user", content="x" * length)]))
                self.assertEqual(response.status_code, status)
                if status == 400:
                    self.answer.assert_not_called()

    def test_empty_or_invalid_history(self):
        for messages in ([], "invalid", [None], [dict(role="assistant", content="answer")]):
            with self.subTest(messages=messages):
                response = self.client.post("/chat", json=dict(messages=messages))
                self.assertEqual(response.status_code, 400)
        self.answer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
