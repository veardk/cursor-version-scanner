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
    compare_versions,
    format_date, 
    get_current_timestamp,
    order_downloads,
    sort_version_entries,
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
        release_candidates = []
        
        # 获取Windows平台下载链接
        for platform in self.PLATFORMS["win32"]["platforms"]:
            download = await self._fetch_latest_download_info(platform)
            if download:
                arch = "x64" if "x64" in platform else "arm64"
                win_urls[arch] = download["url"]
                if download["release"]:
                    release_candidates.append(download["release"])
        
        # 获取Mac平台下载链接
        for platform, display_name in zip(
            self.PLATFORMS["mac"]["platforms"],
            self.PLATFORMS["mac"]["display_names"]
        ):
            download = await self._fetch_latest_download_info(platform)
            if download:
                mac_urls[display_name] = download["url"]
                if download["release"]:
                    release_candidates.append(download["release"])
        
        # 获取Linux平台下载链接
        for platform in self.PLATFORMS["linux"]["platforms"]:
            download = await self._fetch_latest_download_info(platform)
            if download:
                arch = "x64" if "x64" in platform else "arm64"
                linux_urls[arch] = download["url"]
                if download["release"]:
                    release_candidates.append(download["release"])
        
        if win_urls:
            downloads["windows"] = win_urls
        if mac_urls:
            downloads["mac"] = mac_urls
        if linux_urls:
            downloads["linux"] = linux_urls
            
        if not release_candidates:
            logger.error("无法从下载链接中提取版本号或commit_hash")
            return []

        latest_release = release_candidates[0]
        for candidate in release_candidates[1:]:
            if compare_versions(candidate["version"], latest_release["version"]) > 0:
                latest_release = candidate

        version = latest_release["version"]
        commit_hash = latest_release["build_id"]
            
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

    def _extract_release_from_response(self, data: Dict[str, Any], download_url: str) -> Optional[Dict[str, str]]:
        """优先使用 API 元数据提取版本信息，URL 解析只作为兜底"""
        version = data.get("version")
        commit_hash = data.get("commitSha")
        if version and commit_hash:
            return {
                "version": version,
                "build_id": commit_hash,
            }

        return self._extract_release_from_url(download_url)

    def _extract_release_from_url(self, url: Optional[str]) -> Optional[Dict[str, str]]:
        """从下载链接中提取版本号和构建哈希"""
        if not url:
            return None

        version_patterns = (
            r"CursorSetup-(?:x64|arm64)-(\d+\.\d+\.\d+)\.exe",
            r"Cursor-(\d+\.\d+\.\d+)-[a-f0-9]{40}\.deb\.glibc2\.\d+(?:\.\d+)?-(?:x86_64|aarch64)\.AppImage",
            r"Cursor-(\d+\.\d+\.\d+)-(?:x86_64|aarch64)\.AppImage",
        )
        version = None
        for pattern in version_patterns:
            version_match = re.search(pattern, url)
            if version_match:
                version = version_match.group(1)
                break

        commit_match = re.search(r"([a-f0-9]{40})", url)
        if not version or not commit_match:
            return None

        return {
            "version": version,
            "build_id": commit_match.group(1),
        }
    
    def _ensure_complete_downloads(self, version_info: Dict, version: str, commit_hash: str) -> None:
        """确保所有平台都有完整的下载链接"""
        downloads = version_info.setdefault("downloads", {})

        mac_downloads = {
            display_name: f"https://downloads.cursor.com/production/{commit_hash}/darwin/{display_name}/Cursor-darwin-{display_name}.dmg"
            for display_name in self.PLATFORMS["mac"]["display_names"]
        }
        win_downloads = {
            "x64": f"https://downloads.cursor.com/production/{commit_hash}/win32/x64/system-setup/CursorSetup-x64-{version}.exe",
            "arm64": f"https://downloads.cursor.com/production/{commit_hash}/win32/arm64/system-setup/CursorSetup-arm64-{version}.exe"
        }
        linux_downloads = {
            "x64": f"https://downloads.cursor.com/production/{commit_hash}/linux/x64/Cursor-{version}-x86_64.AppImage",
            "arm64": f"https://downloads.cursor.com/production/{commit_hash}/linux/arm64/Cursor-{version}-aarch64.AppImage"
        }

        downloads["mac"] = self._merge_downloads(downloads.get("mac", {}), mac_downloads, version, commit_hash)
        downloads["windows"] = self._merge_downloads(downloads.get("windows", {}), win_downloads, version, commit_hash)
        downloads["linux"] = self._merge_downloads(downloads.get("linux", {}), linux_downloads, version, commit_hash)
                
        # 按mac, windows, linux顺序重新排序平台
        if "downloads" in version_info:
            version_info["downloads"] = order_downloads(version_info["downloads"])

    def _merge_downloads(self, existing: Dict[str, str], expected: Dict[str, str], version: str, commit_hash: str) -> Dict[str, str]:
        """保留已匹配当前版本的直链，仅修复缺失或明显串版的链接"""
        merged_downloads = {}

        for arch, expected_url in expected.items():
            current_url = existing.get(arch)
            if self._is_current_release_url(current_url, version, commit_hash):
                merged_downloads[arch] = current_url
            else:
                merged_downloads[arch] = expected_url

        return merged_downloads

    def _is_current_release_url(self, url: Optional[str], version: str, commit_hash: str) -> bool:
        """判断下载链接是否仍然指向当前版本构建"""
        if not url:
            return False

        version_matches = re.findall(r"\d+\.\d+\.\d+", url)
        if version_matches and version not in version_matches:
            return False

        hash_matches = re.findall(r"[a-f0-9]{40}", url)
        if hash_matches and commit_hash not in hash_matches:
            return False

        return True
    
    async def _fetch_latest_download_info(self, platform: str) -> Optional[Dict[str, Any]]:
        """获取指定平台的最新下载链接和版本元数据"""
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

                release = self._extract_release_from_response(data, download_url)
                    
                logger.debug(f"成功获取 {platform} 平台下载URL: {download_url}")
                return {
                    "url": download_url,
                    "release": release,
                }
                
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
                new_version["downloads"] = order_downloads(new_version["downloads"])
                
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
        return sort_version_entries(all_versions)
