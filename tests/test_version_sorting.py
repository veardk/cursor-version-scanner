import json
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_fetch_all_platforms_prefers_highest_release_across_platforms(self) -> None:
        scanner = CursorVersionScanner("missing.json")
        newer_build = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        older_build = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

        responses = {
            "win32-x64": f"https://downloads.cursor.com/production/{older_build}/win32/x64/system-setup/CursorSetup-x64-2.6.17.exe",
            "win32-arm64": f"https://downloads.cursor.com/production/{older_build}/win32/arm64/system-setup/CursorSetup-arm64-2.6.17.exe",
            "darwin-universal": f"https://downloads.cursor.com/production/{newer_build}/darwin/universal/Cursor-darwin-universal.dmg",
            "darwin-x64": f"https://downloads.cursor.com/production/{newer_build}/darwin/x64/Cursor-darwin-x64.dmg",
            "darwin-arm64": f"https://downloads.cursor.com/production/{newer_build}/darwin/arm64/Cursor-darwin-arm64.dmg",
            "linux-x64": f"https://downloads.cursor.com/production/{newer_build}/linux/x64/Cursor-2.6.18-x86_64.AppImage",
            "linux-arm64": f"https://downloads.cursor.com/production/{newer_build}/linux/arm64/Cursor-2.6.18-aarch64.AppImage",
        }

        async def fake_fetch(platform: str) -> dict:
            return {
                "url": responses[platform],
                "release": scanner._extract_release_from_url(responses[platform]),
            }

        scanner._fetch_latest_download_info = fake_fetch

        result = asyncio.run(scanner._fetch_all_platforms())

        self.assertEqual(result[0]["version"], "2.6.18")
        self.assertEqual(result[0]["build_id"], newer_build)
        self.assertEqual(
            result[0]["downloads"]["windows"]["x64"],
            f"https://downloads.cursor.com/production/{newer_build}/win32/x64/system-setup/CursorSetup-x64-2.6.18.exe",
        )

    def test_extract_release_from_url_supports_legacy_linux_urls(self) -> None:
        scanner = CursorVersionScanner("missing.json")
        build_id = "ae378be9dc2f5f1a6a1a220c6e25f9f03c8d4e19"
        url = (
            "https://anysphere-binaries.s3.us-east-1.amazonaws.com/"
            f"production/client/linux/x64/appimage/Cursor-0.46.11-{build_id}.deb.glibc2.25-x86_64.AppImage"
        )

        release = scanner._extract_release_from_url(url)

        self.assertEqual(
            release,
            {
                "version": "0.46.11",
                "build_id": build_id,
            },
        )

    def test_fetch_all_platforms_uses_api_metadata_when_url_lacks_release_info(self) -> None:
        scanner = CursorVersionScanner("missing.json")
        version = "2.6.18"
        commit_hash = "68fbec5aed9da587d1c6a64172792f505bafa252"
        responses = {
            "win32-x64": {
                "downloadUrl": "https://mirror.example.com/downloads/windows/x64/latest.exe",
                "version": version,
                "commitSha": commit_hash,
            },
            "win32-arm64": {
                "downloadUrl": "https://mirror.example.com/downloads/windows/arm64/latest.exe",
                "version": version,
                "commitSha": commit_hash,
            },
            "darwin-universal": {
                "downloadUrl": "https://mirror.example.com/downloads/macos/universal/latest.dmg",
                "version": version,
                "commitSha": commit_hash,
            },
            "darwin-x64": {
                "downloadUrl": "https://mirror.example.com/downloads/macos/x64/latest.dmg",
                "version": version,
                "commitSha": commit_hash,
            },
            "darwin-arm64": {
                "downloadUrl": "https://mirror.example.com/downloads/macos/arm64/latest.dmg",
                "version": version,
                "commitSha": commit_hash,
            },
            "linux-x64": {
                "downloadUrl": "https://mirror.example.com/downloads/linux/x64/latest.AppImage",
                "version": version,
                "commitSha": commit_hash,
            },
            "linux-arm64": {
                "downloadUrl": "https://mirror.example.com/downloads/linux/arm64/latest.AppImage",
                "version": version,
                "commitSha": commit_hash,
            },
        }

        class FakeResponse:
            status_code = 200

            def __init__(self, data: dict):
                self._data = data

            def json(self) -> dict:
                return self._data

        async def fake_request(url: str, headers=None, timeout: int = 10):
            platform = url.split("platform=")[1].split("&")[0]
            return FakeResponse(responses[platform])

        with patch("src.scanner.async_make_request", side_effect=fake_request):
            result = asyncio.run(scanner._fetch_all_platforms())

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["version"], version)
        self.assertEqual(result[0]["build_id"], commit_hash)
        self.assertEqual(
            result[0]["downloads"]["windows"]["x64"],
            responses["win32-x64"]["downloadUrl"],
        )
        self.assertEqual(
            result[0]["downloads"]["linux"]["arm64"],
            responses["linux-arm64"]["downloadUrl"],
        )

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
