import os
import re
from typing import Dict, List, Any, Optional
import datetime

from src.utils import load_json_file, logger

class ReadmeFormatter:
    """README格式化器，用于更新README文件中的版本表格"""
    
    def __init__(self, data_file: str = "data/versions.json", readme_file: str = "README.md"):
        self.data_file = data_file
        self.readme_file = readme_file
        self.versions_data = load_json_file(data_file)
    
    def update_readme(self) -> bool:
        """更新README文件中的版本表格和更新时间"""
        try:
            with open(self.readme_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 更新最后更新时间
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 使用正则表达式查找并替换最后更新时间
            time_pattern = r'Last Updated \| 最后更新时间: `([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2})`'
            if re.search(time_pattern, content):
                content = re.sub(time_pattern, f'Last Updated | 最后更新时间: `{now}`', content)
            
            # 生成版本表格
            version_table = self._generate_version_table()
            
            # 查找表格开始和结束的位置
            table_pattern = r'\| 版本号.*?Version \| 发布日期.*?Release Date \| macOS \| Windows \| Linux \|\s*\|[-]+\|[-]+\|[-]+\|[-]+\|[-]+\|([\s\S]*?)(?=\s*##|\s*$)'
            match = re.search(table_pattern, content)
            
            if match:
                # 提取表头部分（包括分隔行）
                table_header = content[match.start():match.start() + content[match.start():].find('\n') + 1]
                table_separator = content[match.start() + len(table_header):match.start() + len(table_header) + content[match.start() + len(table_header):].find('\n') + 1]
                
                # 替换旧表格内容
                new_table = f"{table_header}{table_separator}{version_table}"
                content = content[:match.start()] + new_table + content[match.end():]
            else:
                logger.warning("无法在README中找到表格，可能需要手动更新")
                return False
            
            # 写入更新后的内容
            with open(self.readme_file, 'w', encoding='utf-8') as f:
                f.write(content)
                
            logger.info(f"README更新成功: {self.readme_file}")
            return True
            
        except Exception as e:
            logger.error(f"更新README时出错: {e}")
            return False
    
    def _generate_version_table(self) -> str:
        """生成版本表格"""
        table_rows = []
        
        for version_info in self.versions_data["versions"]:
            version = version_info.get("version", "")
            date = version_info.get("date", "")
            
            # 处理下载链接
            mac_links = []
            win_links = []
            linux_links = []
            
            # 处理各平台下载链接
            for download_type, downloads in version_info.get("downloads", {}).items():
                if download_type == "mac":
                    for arch, url in downloads.items():
                        if arch == "universal":
                            mac_links.append(f"[Universal]({url})")
                        elif arch == "x64":
                            mac_links.append(f"[x64]({url})")
                        elif arch == "arm64":
                            mac_links.append(f"[ARM64]({url})")
                elif download_type == "windows":
                    for arch, url in downloads.items():
                        if arch == "x64":
                            win_links.append(f"[x64]({url})")
                        elif arch == "arm64":
                            win_links.append(f"[ARM64]({url})")
                elif download_type == "linux":
                    for arch, url in downloads.items():
                        if arch == "x64":
                            linux_links.append(f"[x64]({url})")
                        elif arch == "arm64":
                            linux_links.append(f"[ARM64]({url})")
            
            # 格式化列内容
            mac_column = " ".join(mac_links) if mac_links else "暂无"
            win_column = " ".join(win_links) if win_links else "暂无"
            linux_column = " ".join(linux_links) if linux_links else "暂无"
            
            # 添加表格行
            table_rows.append(f"| {version} | {date} | {mac_column} | {win_column} | {linux_column} |")
        
        return "\n".join(table_rows) 