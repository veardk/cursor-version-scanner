import json
import tempfile
import unittest
from pathlib import Path

from src.formatter import ReadmeFormatter
from src.scanner import CursorVersionScanner


def make_version(version: str) -> dict:
    return {
        "version": version,
        "date": "2025-01-01",
        "build_id": f"build-{version}",
        "downloads": {},
    }


class VersionSortingTests(unittest.TestCase):
    def test_process_versions_uses_semantic_version_order(self) -> None:
        scanner = CursorVersionScanner("missing.json")
        scanner.versions_data = {
            "versions": [
                make_version("1.6.6"),
                make_version("1.6.45"),
                make_version("1.5.2"),
                make_version("1.5.11"),
            ]
        }

        result = scanner.process_versions([make_version("1.6.45"), make_version("1.5.11")])

        self.assertEqual(
            [item["version"] for item in result],
            ["1.6.45", "1.6.6", "1.5.11", "1.5.2"],
        )

    def test_ensure_complete_downloads_replaces_cross_version_urls(self) -> None:
        scanner = CursorVersionScanner("missing.json")
        version = "1.5.8"
        build_id = "d1893fd7f5de2b705e0c040fb710b08f6afd4239"
        version_info = {
            "downloads": {
                "linux": {
                    "x64": "https://downloads.cursor.com/production/6aa7b3af0d578b9a3aa3ab443571e1a51ebb4e83/linux/x64/Cursor-1.5.7-x86_64.AppImage",
                    "arm64": "https://downloads.cursor.com/production/6aa7b3af0d578b9a3aa3ab443571e1a51ebb4e83/linux/arm64/Cursor-1.5.7-aarch64.AppImage",
                }
            }
        }

        scanner._ensure_complete_downloads(version_info, version, build_id)

        self.assertEqual(
            version_info["downloads"]["linux"],
            {
                "x64": f"https://downloads.cursor.com/production/{build_id}/linux/x64/Cursor-{version}-x86_64.AppImage",
                "arm64": f"https://downloads.cursor.com/production/{build_id}/linux/arm64/Cursor-{version}-aarch64.AppImage",
            },
        )

    def test_ensure_complete_downloads_preserves_matching_urls(self) -> None:
        scanner = CursorVersionScanner("missing.json")
        version = "1.5.8"
        build_id = "d1893fd7f5de2b705e0c040fb710b08f6afd4239"
        current_linux = {
            "x64": f"https://mirror.example.com/releases/{version}/cursor-linux-x64.AppImage",
            "arm64": f"https://mirror.example.com/releases/{version}/cursor-linux-arm64.AppImage",
        }
        version_info = {
            "downloads": {
                "linux": dict(current_linux),
            }
        }

        scanner._ensure_complete_downloads(version_info, version, build_id)

        self.assertEqual(version_info["downloads"]["linux"], current_linux)

    def test_readme_formatter_sorts_versions_before_rendering(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "versions.json"
            readme_file = Path(temp_dir) / "README.md"

            data_file.write_text(
                json.dumps(
                    {
                        "versions": [
                            make_version("0.46.2"),
                            make_version("0.46.11"),
                            make_version("0.45.2"),
                            make_version("0.45.15"),
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            readme_file.write_text("placeholder", encoding="utf-8")

            formatter = ReadmeFormatter(str(data_file), str(readme_file))
            rows = formatter._generate_version_table().splitlines()

            self.assertEqual(
                [row.split("|")[1].strip() for row in rows],
                ["0.46.11", "0.46.2", "0.45.15", "0.45.2"],
            )

    def test_update_readme_uses_data_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "versions.json"
            readme_file = Path(temp_dir) / "README.md"
            last_updated = "2025-10-01 12:23:00"

            data_file.write_text(
                json.dumps(
                    {
                        "versions": [make_version("1.6.45"), make_version("1.6.6")],
                        "last_updated": last_updated,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            readme_file.write_text(
                "\n".join(
                    [
                        "### Version History",
                        "",
                        "Last Updated | 最后更新时间:  `2024-01-01 00:00:00`",
                        "",
                        "| 版本号<br>Version | 发布日期<br>Release Date | macOS | Windows | Linux |",
                        "|--------|----------|-------|---------|-------|",
                        "| 0.0.1 | 2024-01-01 | 暂无 | 暂无 | 暂无 |",
                    ]
                ),
                encoding="utf-8",
            )

            formatter = ReadmeFormatter(str(data_file), str(readme_file))

            self.assertTrue(formatter.update_readme())
            content = readme_file.read_text(encoding="utf-8")

            self.assertIn(f"Last Updated | 最后更新时间:  `{last_updated}`", content)


if __name__ == "__main__":
    unittest.main()
