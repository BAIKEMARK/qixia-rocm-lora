import tempfile
import unittest
from pathlib import Path

from scripts.validate_dataset import DatasetValidationError, validate_dataset_file, validate_rows


class ValidateDatasetTests(unittest.TestCase):
    def test_validate_sharegpt_rows_returns_stats(self):
        rows = [
            {
                "system": "角色系统提示",
                "conversations": [
                    {"from": "human", "value": "如果规则看起来矛盾，你会怎么判断？"},
                    {"from": "gpt", "value": "先别急。先把已知条件列清楚。"},
                ],
            }
        ]

        stats = validate_rows(rows)

        self.assertEqual(stats["examples"], 1)
        self.assertEqual(stats["min_turns"], 2)
        self.assertEqual(stats["max_turns"], 2)
        self.assertGreater(stats["avg_user_chars"], 0)
        self.assertGreater(stats["avg_assistant_chars"], 0)

    def test_rejects_rows_without_assistant_reply(self):
        rows = [
            {
                "conversations": [
                    {"from": "human", "value": "问题"},
                ],
            }
        ]

        with self.assertRaises(DatasetValidationError):
            validate_rows(rows)

    def test_validate_dataset_file_reads_json_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dataset.json"
            path.write_text(
                '[{"conversations":[{"from":"human","value":"问题"},{"from":"gpt","value":"回答"}]}]',
                encoding="utf-8",
            )

            stats = validate_dataset_file(path)

        self.assertEqual(stats["examples"], 1)


if __name__ == "__main__":
    unittest.main()
