"""Regression contract: leaderboard visibility and database-side top-10 limits."""
import ast
from pathlib import Path
import unittest


class LeaderboardQueryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "app" / "routers" / "sync.py"
        cls.source = path.read_text(encoding="utf-8")
        cls.module = ast.parse(cls.source, filename=str(path))
        cls.endpoint = next(
            node for node in cls.module.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "leaderboard"
        )

    def test_leaderboard_requires_current_user(self):
        args = self.endpoint.args.args
        names = [arg.arg for arg in args]
        self.assertIn("current", names)
        self.assertNotIn("credentials", names)

        index = names.index("current")
        arg_index_from_end = len(args) - index
        default = self.endpoint.args.defaults[-arg_index_from_end]
        self.assertIsInstance(default, ast.Call)
        self.assertIsInstance(default.func, ast.Name)
        self.assertEqual(default.func.id, "Depends")
        self.assertEqual(ast.unparse(default.args[0]), "get_current_user")

    def test_query_limit_is_hard_capped_at_ten(self):
        names = [arg.arg for arg in self.endpoint.args.args]
        index = names.index("limit")
        default = self.endpoint.args.defaults[-(len(names) - index)]
        self.assertIsInstance(default, ast.Call)
        self.assertEqual(ast.unparse(default.func), "Query")
        self.assertEqual(default.args[0].value, 10)
        kwargs = {kw.arg: kw.value.value for kw in default.keywords}
        self.assertEqual(kwargs.get("ge"), 1)
        self.assertEqual(kwargs.get("le"), 10)

    def test_all_materialized_user_queries_apply_limit_before_all(self):
        all_calls = [
            node for node in ast.walk(self.endpoint)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "all"
        ]
        self.assertGreaterEqual(len(all_calls), 3)
        for call in all_calls:
            with self.subTest(line=call.lineno):
                self.assertIsInstance(call.func.value, ast.Call)
                limited_query = call.func.value
                self.assertIsInstance(limited_query.func, ast.Attribute)
                self.assertEqual(limited_query.func.attr, "limit")
                self.assertEqual(ast.unparse(limited_query.args[0]), "limit")

    def test_profile_visibility_is_filtered_in_sql_and_weekly_uses_join(self):
        attrs = {
            node.attr for node in ast.walk(self.endpoint)
            if isinstance(node, ast.Attribute)
        }
        self.assertIn("profile_visibility", attrs)
        self.assertIn("filter", attrs)

        joins = [
            node for node in ast.walk(self.endpoint)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "join"
        ]
        self.assertTrue(any(
            node.args and ast.unparse(node.args[0]) == "User"
            for node in joins
        ))


if __name__ == "__main__":
    unittest.main()
