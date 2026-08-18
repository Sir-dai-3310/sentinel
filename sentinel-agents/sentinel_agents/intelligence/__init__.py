"""Threat intelligence integrations."""

import os
from abc import ABC, abstractmethod

import httpx

from sentinel_agents.state import ThreatIntel


class ThreatIntelProvider(ABC):
    """Base class for threat intelligence providers."""

    @abstractmethod
    async def lookup_ip(self, ip: str) -> ThreatIntel | None:
        """Lookup IP address."""
        pass

    @abstractmethod
    async def lookup_hash(self, file_hash: str) -> ThreatIntel | None:
        """Lookup file hash."""
        pass

    @abstractmethod
    async def lookup_domain(self, domain: str) -> ThreatIntel | None:
        """Lookup domain."""
        pass


class VirusTotalProvider(ThreatIntelProvider):
    """VirusTotal API integration."""

    BASE_URL = "https://www.virustotal.com/api/v3"

    def __init__(self):
        self.api_key = os.getenv("VT_API_KEY")
        if not self.api_key:
            raise ValueError("VT_API_KEY not set")

        self.client = httpx.AsyncClient(
            headers={"x-apikey": self.api_key},
            timeout=30.0,
        )

    async def lookup_ip(self, ip: str) -> ThreatIntel | None:
        """Lookup IP on VirusTotal."""
        try:
            response = await self.client.get(f"{self.BASE_URL}/ip_addresses/{ip}")
            response.raise_for_status()
            data = response.json()

            stats = data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
            malicious = stats.get("malicious", 0) > 0

            return ThreatIntel(
                source="VirusTotal",
                ioc_type="ip",
                ioc_value=ip,
                malicious=malicious,
                confidence=90 if malicious else 10,
                details=data,
            )
        except Exception as e:
            print(f"VirusTotal lookup failed: {e}")
            return None

    async def lookup_hash(self, file_hash: str) -> ThreatIntel | None:
        """Lookup file hash on VirusTotal."""
        try:
            response = await self.client.get(f"{self.BASE_URL}/files/{file_hash}")
            response.raise_for_status()
            data = response.json()

            stats = data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
            malicious = stats.get("malicious", 0) > 0

            return ThreatIntel(
                source="VirusTotal",
                ioc_type="hash",
                ioc_value=file_hash,
                malicious=malicious,
                confidence=95 if malicious else 5,
                details=data,
            )
        except Exception as e:
            print(f"VirusTotal lookup failed: {e}")
            return None

    async def lookup_domain(self, domain: str) -> ThreatIntel | None:
        """Lookup domain on VirusTotal."""
        try:
            response = await self.client.get(f"{self.BASE_URL}/domains/{domain}")
            response.raise_for_status()
            data = response.json()

            stats = data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
            malicious = stats.get("malicious", 0) > 0

            return ThreatIntel(
                source="VirusTotal",
                ioc_type="domain",
                ioc_value=domain,
                malicious=malicious,
                confidence=85 if malicious else 15,
                details=data,
            )
        except Exception as e:
            print(f"VirusTotal lookup failed: {e}")
            return None


class AbuseIPDBProvider(ThreatIntelProvider):
    """AbuseIPDB API integration."""

    BASE_URL = "https://api.abuseipdb.com/api/v2"

    def __init__(self):
        self.api_key = os.getenv("ABUSEIPDB_API_KEY")
        if not self.api_key:
            raise ValueError("ABUSEIPDB_API_KEY not set")

        self.client = httpx.AsyncClient(
            headers={"Key": self.api_key, "Accept": "application/json"},
            timeout=30.0,
        )

    async def lookup_ip(self, ip: str) -> ThreatIntel | None:
        """Lookup IP on AbuseIPDB."""
        try:
            response = await self.client.get(
                f"{self.BASE_URL}/check",
                params={"ipAddress": ip, "maxAgeInDays": 90},
            )
            response.raise_for_status()
            data = response.json()

            abuse_confidence = data.get("data", {}).get("abuseConfidenceScore", 0)
            malicious = abuse_confidence > 50

            return ThreatIntel(
                source="AbuseIPDB",
                ioc_type="ip",
                ioc_value=ip,
                malicious=malicious,
                confidence=abuse_confidence,
                details=data,
            )
        except Exception as e:
            print(f"AbuseIPDB lookup failed: {e}")
            return None

    async def lookup_hash(self, file_hash: str) -> ThreatIntel | None:
        """Not supported by AbuseIPDB."""
        return None

    async def lookup_domain(self, domain: str) -> ThreatIntel | None:
        """Not supported by AbuseIPDB."""
        return None


class IntelligenceAggregator:
    """Aggregate threat intelligence from multiple providers."""

    def __init__(self, providers: list[ThreatIntelProvider]):
        self.providers = providers

    async def _lookup_with_retry(self, method, value: str) -> ThreatIntel | None:
        """
        Call a provider lookup with retry on transient (retryable) errors.

        Providers that catch their own exceptions return None; a provider that
        raises a retryable network error is retried with exponential backoff.
        Persistent failure is tolerated (returns None) so intel never blocks
        analysis.
        """
        from sentinel_agents.utils.retry import call_with_retry

        try:
            return await call_with_retry(method, value)
        except Exception:
            return None

    async def lookup_ip(self, ip: str) -> list[ThreatIntel]:
        """Lookup IP across all providers."""
        results = []
        for provider in self.providers:
            result = await self._lookup_with_retry(provider.lookup_ip, ip)
            if result:
                results.append(result)
        return results

    async def lookup_hash(self, file_hash: str) -> list[ThreatIntel]:
        """Lookup hash across all providers."""
        results = []
        for provider in self.providers:
            result = await self._lookup_with_retry(provider.lookup_hash, file_hash)
            if result:
                results.append(result)
        return results

    async def lookup_domain(self, domain: str) -> list[ThreatIntel]:
        """Lookup domain across all providers."""
        results = []
        for provider in self.providers:
            result = await self._lookup_with_retry(provider.lookup_domain, domain)
            if result:
                results.append(result)
        return results
