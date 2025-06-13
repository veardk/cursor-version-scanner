import os
import json
import logging
import requests
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('cursor-scanner')

def ensure_dir_exists(directory: str) -> None:
    """确保目录存在，不存在则创建"""
    if not directory:
        return
        
    if not os.path.exists(directory):
        logger.info(f"确保目录存在: {directory}")
        try:
            os.makedirs(directory, exist_ok=True)
        except Exception as e:
            logger.error(f"创建目录失败: {directory}, 错误: {e}")

def load_json_file(file_path: str, default_value: Any = None) -> Any:
    """从JSON文件加载数据"""
    if not os.path.exists(file_path):
        logger.warning(f"文件不存在: {file_path}, 返回默认值")
        return default_value
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"读取JSON文件失败: {file_path}, 错误: {e}")
        return default_value

def save_json_file(file_path: str, data: Dict, ensure_dir: bool = True) -> bool:
    """保存JSON数据到文件"""
    if ensure_dir:
        ensure_dir_exists(os.path.dirname(file_path))
        
    try:
        # 确保版本下载链接顺序一致
        if "versions" in data:
            for version in data["versions"]:
                if "downloads" in version:
                    ordered_downloads = {}
                    for platform in ["mac", "windows", "linux"]:
                        if platform in version["downloads"]:
                            ordered_downloads[platform] = version["downloads"][platform]
                    version["downloads"] = ordered_downloads
                    
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存JSON文件失败: {e}")
        return False

def make_request(url: str, headers: Dict = None, timeout: int = 10) -> Optional[requests.Response]:
    """发送HTTP请求并返回响应"""
    default_headers = {
        'User-Agent': 'Cursor-Version-Scanner',
        'Cache-Control': 'no-cache',
    }
    
    if headers:
        default_headers.update(headers)
    
    try:
        response = requests.get(url, headers=default_headers, timeout=timeout)
        return response
    except Exception as e:
        logger.error(f"请求失败: {url}, 错误: {e}")
        return None

async def async_make_request(url: str, headers: Dict = None, timeout: int = 10) -> Optional[requests.Response]:
    """异步发送HTTP请求并返回响应"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: make_request(url, headers, timeout))

def format_date(date_str: Any) -> str:
    """格式化日期字符串为YYYY-MM-DD格式"""
    if isinstance(date_str, datetime):
        return date_str.strftime("%Y-%m-%d")
        
    if not date_str:
        return datetime.now().strftime("%Y-%m-%d")
        
    try:
        # 尝试解析ISO格式日期
        if isinstance(date_str, str):
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d")
    except ValueError:
        pass
            
    # 如果所有尝试都失败，返回当前日期
    return datetime.now().strftime("%Y-%m-%d")

def compare_versions(version1: str, version2: str) -> int:
    """比较两个版本号"""
    try:
        v1_parts = [int(part) for part in version1.split('.')]
        v2_parts = [int(part) for part in version2.split('.')]
        
        # 确保两个版本号有相同的部分数
        while len(v1_parts) < len(v2_parts):
            v1_parts.append(0)
        while len(v2_parts) < len(v1_parts):
            v2_parts.append(0)
            
        # 比较每个部分
        for i in range(len(v1_parts)):
            if v1_parts[i] > v2_parts[i]:
                return 1
            elif v1_parts[i] < v2_parts[i]:
                return -1
                
        return 0
    except Exception as e:
        logger.error(f"版本比较失败: {version1} vs {version2}, 错误: {e}")
        # 回退到字符串比较
        if version1 > version2:
            return 1
        elif version1 < version2:
            return -1
        else:
            return 0

def get_current_timestamp() -> str:
    """获取当前时间戳，格式为YYYY-MM-DD HH:MM:SS"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S") 