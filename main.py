import os
import sys
import argparse
import asyncio
from src.scanner import CursorVersionScanner
from src.formatter import ReadmeFormatter
from src.utils import logger, ensure_dir_exists

async def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="Cursor版本扫描器")
    parser.add_argument("--data-file", default="data/versions.json", help="版本数据文件路径")
    parser.add_argument("--readme-file", default="README.md", help="README文件路径")
    parser.add_argument("--update-only", action="store_true", help="只更新版本数据，不更新README")
    parser.add_argument("--verbose", action="store_true", help="显示详细日志")
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        logger.setLevel("DEBUG")
    
    # 确保目录存在
    data_dir = os.path.dirname(args.data_file)
    ensure_dir_exists(data_dir)
    
    # 更新版本数据
    scanner = CursorVersionScanner(args.data_file)
    success = await scanner.update_versions()
    
    if not success:
        logger.error("更新版本数据失败")
        sys.exit(1)
    
    # 更新README
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