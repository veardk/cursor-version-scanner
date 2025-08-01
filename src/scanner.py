import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
import json
import os
import re
from src.utils import logger, save_json_file

from src.utils import (
    load_json_file, 
    async_make_request,
    format_date, 
    get_current_timestamp,
)

class CursorVersionScanner:
    
    API_ENDPOINT = "https://www.cursor.com/api/download?platform={platform}&releaseTrack=latest"
    
    PLATFORMS = {
        "win32": {
            "platforms": ["win32-x64", "win32-arm64"],
            "file_patterns": [
                r"win32/x64/system-setup/CursorSetup-x64-(\d+\.\d+\.\d+)\.exe",
                r"win32/arm64/system-setup/CursorSetup-arm64-(\d+\.\d+\.\d+)\.exe"
            ]
        },
        "mac": {
            "platforms": ["darwin-universal", "darwin-x64", "darwin-arm64"],
            "display_names": ["universal", "x64", "arm64"]
        },
        "linux": {
            "platforms": ["linux-x64", "linux-arm64"],
            "file_patterns": [
                r"linux/x64/Cursor-(\d+\.\d+\.\d+)-x86_64\.AppImage",
                r"linux/arm64/Cursor-(\d+\.\d+\.\d+)-aarch64\.AppImage"
            ]
        }
    }
    
    def __init__(self, data_file: str):
        self.data_file = data_file
        self.versions_data = self._load_versions_data()
        
    def _get_current_date(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")
        
    def _load_versions_data(self) -> Dict:
        """加载版本数据"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # 确保数据格式正确
                if not isinstance(data, dict):
                    logger.warning(f"版本数据格式不正确: {self.data_file}")
                    return {"versions": []}
                    
                if "versions" not in data:
                    data["versions"] = []
                    
                logger.debug(f"成功加载版本数据: {self.data_file}, 共 {len(data.get('versions', []))} 个版本")
                return data
            except Exception as e:
                logger.error(f"加载版本数据失败: {self.data_file}, 错误: {e}")
                return {"versions": []}
        else:
            logger.info(f"版本数据文件不存在，将创建新文件: {self.data_file}")
            return {"versions": []}

    async def check_new_version(self) -> bool:
        """检查是否有新版本"""
        logger.info("检查是否有新版本")

        new_versions = await self._fetch_all_platforms()

        if not new_versions:
            logger.warning("未获取到版本信息")
            return False

        new_version = new_versions[0]
        existing_versions = self.versions_data.get("versions", [])

        for existing in existing_versions:
            if existing.get("version") == new_version.get("version"):
                logger.debug(f"版本 {new_version.get('version')} 已存在")
                return False

        logger.info(f"发现新版本: {new_version.get('version')}")
        return True

    async def update_versions(self) -> bool:
        """更新版本数据"""
        logger.info("开始更新版本数据")

        logger.info("开始获取最新版本信息")
        new_versions = await self._fetch_all_platforms()

        if not new_versions:
            logger.warning("未获取到新版本信息")
            return False

        versions = self.process_versions(new_versions)

        self.versions_data["versions"] = versions
        self.versions_data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if save_json_file(self.data_file, self.versions_data):
            logger.info(f"已成功保存数据到: {self.data_file}")
            logger.info(f"成功更新版本数据，共 {len(versions)} 个版本")
            return True
        else:
            logger.error(f"保存数据失败: {self.data_file}")
            return False
        
    async def _fetch_all_platforms(self) -> List[Dict]:
        """获取所有平台的下载URL"""
        downloads = {}
        win_urls = {}
        mac_urls = {}
        linux_urls = {}
        
        # 获取Windows平台下载链接
        for platform in self.PLATFORMS["win32"]["platforms"]:
            url = await self._fetch_latest_download_url(platform)
            if url:
                version_match = re.search(r"CursorSetup-(?:x64|arm64)-(\d+\.\d+\.\d+)\.exe", url)
                if version_match:
                    version = version_match.group(1)
                    arch = "x64" if "x64" in platform else "arm64"
                    win_urls[arch] = url
        
        # 获取Mac平台下载链接
        for platform, display_name in zip(
            self.PLATFORMS["mac"]["platforms"],
            self.PLATFORMS["mac"]["display_names"]
        ):
            url = await self._fetch_latest_download_url(platform)
            if url:
                mac_urls[display_name] = url
        
        # 获取Linux平台下载链接
        for platform in self.PLATFORMS["linux"]["platforms"]:
            url = await self._fetch_latest_download_url(platform)
            if url:
                arch = "x64" if "x64" in platform else "arm64"
                linux_urls[arch] = url
        
        if win_urls:
            downloads["windows"] = win_urls
        if mac_urls:
            downloads["mac"] = mac_urls
        if linux_urls:
            downloads["linux"] = linux_urls
            
        # 从URL中提取版本号和commit_hash
        version = None
        commit_hash = None
        
        # 尝试从Windows下载链接中提取
        for url in win_urls.values():
            if url:
                version_match = re.search(r"CursorSetup-(?:x64|arm64)-(\d+\.\d+\.\d+)\.exe", url)
                commit_match = re.search(r"production/([a-f0-9]{40})/", url)
                if version_match:
                    version = version_match.group(1)
                if commit_match:
                    commit_hash = commit_match.group(1)
                if version and commit_hash:
                    break
        
        # 如果Windows链接中没有提取到，尝试从Linux下载链接中提取
        if not version or not commit_hash:
            for url in linux_urls.values():
                if url:
                    version_match = re.search(r"Cursor-(\d+\.\d+\.\d+)-(?:x86_64|aarch64)\.AppImage", url)
                    commit_match = re.search(r"production/([a-f0-9]{40})/", url)
                    if version_match and not version:
                        version = version_match.group(1)
                    if commit_match and not commit_hash:
                        commit_hash = commit_match.group(1)
                    if version and commit_hash:
                        break
                        
        # 如果仍然没有提取到，返回空列表
        if not version or not commit_hash:
            logger.error("无法从下载链接中提取版本号或commit_hash")
            return []
            
        # 构建版本信息
        version_info = {
            "version": version,
            "date": self._get_current_date(),
            "build_id": commit_hash,
            "downloads": downloads
        }
        
        # 确保所有平台都有完整的下载链接
        self._ensure_complete_downloads(version_info, version, commit_hash)
        
        return [version_info]
    
    def _ensure_complete_downloads(self, version_info: Dict, version: str, commit_hash: str) -> None:
        """确保所有平台都有完整的下载链接"""
        # 确保Mac下载链接完整
        if "mac" not in version_info["downloads"]:
            version_info["downloads"]["mac"] = {}
            
        # 检查并添加缺失的Mac链接
        for platform, display_name in zip(
            self.PLATFORMS["mac"]["platforms"],
            self.PLATFORMS["mac"]["display_names"]
        ):
            if display_name not in version_info["downloads"]["mac"]:
                mac_url = f"https://downloads.cursor.com/production/{commit_hash}/darwin/{display_name}/Cursor-darwin-{display_name}.dmg"
                version_info["downloads"]["mac"][display_name] = mac_url
        
        # 确保Windows下载链接完整
        if "windows" not in version_info["downloads"]:
            version_info["downloads"]["windows"] = {}
            
        # 只保留Windows的x64和arm64系统安装版
        win_platforms = {
            "x64": f"https://downloads.cursor.com/production/{commit_hash}/win32/x64/system-setup/CursorSetup-x64-{version}.exe",
            "arm64": f"https://downloads.cursor.com/production/{commit_hash}/win32/arm64/system-setup/CursorSetup-arm64-{version}.exe"
        }
        
        for display_name, url in win_platforms.items():
            if display_name not in version_info["downloads"]["windows"]:
                version_info["downloads"]["windows"][display_name] = url
            
        # 确保Linux下载链接完整
        if "linux" not in version_info["downloads"]:
            version_info["downloads"]["linux"] = {}
            
        # 检查并添加缺失的Linux链接
        linux_platforms = {
            "x64": f"https://downloads.cursor.com/production/{commit_hash}/linux/x64/Cursor-{version}-x86_64.AppImage",
            "arm64": f"https://downloads.cursor.com/production/{commit_hash}/linux/arm64/Cursor-{version}-aarch64.AppImage"
        }
        
        for display_name, url in linux_platforms.items():
            if display_name not in version_info["downloads"]["linux"]:
                version_info["downloads"]["linux"][display_name] = url
                
        # 按mac, windows, linux顺序重新排序平台
        if "downloads" in version_info:
            ordered_downloads = {}
            for platform in ["mac", "windows", "linux"]:
                if platform in version_info["downloads"]:
                    ordered_downloads[platform] = version_info["downloads"][platform]
            version_info["downloads"] = ordered_downloads
    
    async def _fetch_latest_download_url(self, platform: str) -> Optional[str]:
        """获取指定平台的最新下载URL"""
        # 处理特殊系统版本URL
        api_platform = platform
        is_system_version = False
        
        if platform.endswith('-system'):
            api_platform = platform.replace('-system', '')
            is_system_version = True
        
        url = self.API_ENDPOINT.format(platform=api_platform)
        logger.debug(f"尝试获取 {platform} 平台下载URL: {url}")
        
        try:
            response = await async_make_request(url)
            if not response or response.status_code != 200:
                logger.warning(f"获取 {platform} 平台下载URL失败: {response.status_code if response else 'No response'}")
                return None
                
            # 解析响应
            try:
                data = response.json()
                download_url = data.get("downloadUrl", "")
                
                # 处理系统版本URL
                if is_system_version:
                    download_url = download_url.replace('user-setup/CursorUserSetup', 'system-setup/CursorSetup')
                
                if not download_url:
                    logger.warning(f"{platform} 平台没有下载链接")
                    return None
                    
                logger.debug(f"成功获取 {platform} 平台下载URL: {download_url}")
                return download_url
                
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"解析 {platform} 平台响应失败: {e}")
                return None
                
        except Exception as e:
            logger.error(f"获取 {platform} 平台下载URL时出错: {e}")
            return None
    
    def process_versions(self, new_versions: List[Dict]) -> List[Dict]:
        """处理版本信息，合并新旧版本"""
        if not new_versions:
            return []
            
        # 获取现有版本
        existing_versions = self.versions_data.get("versions", [])
        
        # 合并版本
        merged_versions = []
        for new_version in new_versions:
            # 确保平台顺序一致
            if "downloads" in new_version:
                ordered_downloads = {}
                for platform in ["mac", "windows", "linux"]:
                    if platform in new_version["downloads"]:
                        ordered_downloads[platform] = new_version["downloads"][platform]
                new_version["downloads"] = ordered_downloads
                
            # 检查是否已存在相同版本
            version_exists = False
            for existing in existing_versions:
                if existing.get("version") == new_version.get("version"):
                    version_exists = True
                    break
                    
            if not version_exists:
                merged_versions.append(new_version)
                
        # 合并新旧版本
        all_versions = existing_versions + merged_versions
        
        # 按版本号排序
        all_versions.sort(key=lambda x: x.get("version", "0.0.0"), reverse=True)
        
        return all_versions 