import os
import sys
import argparse
import asyncio
from src.scanner import CursorVersionScanner
from src.formatter import ReadmeFormatter
from src.utils import logger

async def main():
    parser = argparse.ArgumentParser(description="Cursor版本扫描器")
    parser.add_argument("--data-file", default="versions.json", help="版本数据文件路径")
    parser.add_argument("--readme-file", default="README.md", help="README文件路径")
    parser.add_argument("--update-only", action="store_true", help="只更新版本数据，不更新README")
    parser.add_argument("--check-only", action="store_true", help="只检查是否有新版本")
    parser.add_argument("--verbose", action="store_true", help="显示详细日志")
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel("DEBUG")

    scanner = CursorVersionScanner(args.data_file)

    if args.check_only:
        has_new = await scanner.check_new_version()
        if has_new:
            logger.info("检测到新版本")
            sys.exit(0)
        else:
            logger.info("没有新版本")
            sys.exit(1)

    success = await scanner.update_versions()

    if not success:
        logger.error("更新版本数据失败")
        sys.exit(1)

    if not args.update_only:
        formatter = ReadmeFormatter(args.data_file, args.readme_file)
        success = formatter.update_readme()

        if not success:
            logger.error("更新README失败")
            sys.exit(1)

    logger.info("处理完成")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("用户中断")
        sys.exit(0)
    except Exception as e:
        logger.error(f"发生错误: {e}")
        sys.exit(1) 