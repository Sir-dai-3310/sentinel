"""IOC extraction from log events."""

import re
from typing import Any


class IOCExtractor:
    """Extract Indicators of Compromise from log events."""

    # Regex patterns
    IPV4_PATTERN = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
    DOMAIN_PATTERN = r'\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b'
    MD5_PATTERN = r'\b[a-fA-F0-9]{32}\b'
    SHA256_PATTERN = r'\b[a-fA-F0-9]{64}\b'
    URL_PATTERN = r'https?://[^\s<>"{}|\\^`\[\]]+'

    @staticmethod
    def extract(log: dict[str, Any]) -> dict[str, list[str]]:
        """
        Extract all IOCs from a log event.

        Args:
            log: Log event dictionary

        Returns:
            Dictionary with keys: ips, domains, hashes, urls
        """
        # Convert log to string for pattern matching
        log_str = str(log)

        return {
            "ips": IOCExtractor._extract_ips(log_str),
            "domains": IOCExtractor._extract_domains(log_str),
            "hashes": IOCExtractor._extract_hashes(log_str),
            "urls": IOCExtractor._extract_urls(log_str),
        }

    @staticmethod
    def _extract_ips(text: str) -> list[str]:
        """Extract IPv4 addresses."""
        ips = re.findall(IOCExtractor.IPV4_PATTERN, text)
        # Filter out invalid IPs
        return [ip for ip in ips if IOCExtractor._is_valid_ip(ip)]

    @staticmethod
    def _is_valid_ip(ip: str) -> bool:
        """Check if IP is valid and not private."""
        parts = ip.split('.')
        if len(parts) != 4:
            return False

        try:
            nums = [int(p) for p in parts]
            if any(n > 255 for n in nums):
                return False

            # Filter out private IPs
            if nums[0] == 10:
                return False
            if nums[0] == 172 and 16 <= nums[1] <= 31:
                return False
            if nums[0] == 192 and nums[1] == 168:
                return False
            if nums[0] == 127:
                return False

            return True
        except ValueError:
            return False

    @staticmethod
    def _extract_domains(text: str) -> list[str]:
        """Extract domain names."""
        domains = re.findall(IOCExtractor.DOMAIN_PATTERN, text, re.IGNORECASE)
        # Filter out common false positives
        blacklist = {'windows.com', 'microsoft.com', 'localhost'}
        return [d for d in domains if d.lower() not in blacklist]

    @staticmethod
    def _extract_hashes(text: str) -> list[str]:
        """Extract file hashes (MD5, SHA256)."""
        md5s = re.findall(IOCExtractor.MD5_PATTERN, text)
        sha256s = re.findall(IOCExtractor.SHA256_PATTERN, text)
        return md5s + sha256s

    @staticmethod
    def _extract_urls(text: str) -> list[str]:
        """Extract URLs."""
        urls = re.findall(IOCExtractor.URL_PATTERN, text)
        # Filter out common false positives
        blacklist = {'microsoft.com', 'windows.com', 'schemas.microsoft.com'}
        return [u for u in urls if not any(b in u for b in blacklist)]
