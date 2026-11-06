import re
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class ExtractedEntities(BaseModel):
    """Structured container for all high-value extracted business entities."""

    dates: list[str] = Field(default_factory=list)
    currencies: list[dict[str, Any]] = Field(default_factory=list)
    tax_ids: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    phone_numbers: list[str] = Field(default_factory=list)
    key_values: dict[str, str] = Field(default_factory=dict)


class EntityExtractor:
    """Extracts business-critical structured entities and key-value pairs from text."""

    # Regex patterns
    DATE_PATTERNS = [
        r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b",  # dd/mm/yyyy or dd-mm-yyyy
        r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b",  # yyyy-mm-dd or yyyy/mm/dd
    ]

    CURRENCY_PATTERN = re.compile(
        r"(?:(?:VNĐ|VND|\$|USD|EUR|€)\s*[\d,.]+|[\d,.]+\s*(?:VNĐ|VND|USD|EUR|đồng|dong|\$|€))",
        re.IGNORECASE,
    )

    TAX_ID_PATTERN = re.compile(r"\b\d{10}(?:-\d{3})?\b")
    EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    PHONE_PATTERN = re.compile(r"\b(?:\+84|0)(?:[35789]\d{8}|[2]\d{9})\b")

    KVP_PATTERN = re.compile(
        r"^[ \t]*([A-Za-zÀ-ỹ0-9_.\s\-#]{2,40})[ \t]*[:：][ \t]*(.+)$",
        re.MULTILINE,
    )

    def extract_dates(self, text: str) -> list[str]:
        found_dates = set()
        # dd/mm/yyyy
        for match in re.finditer(self.DATE_PATTERNS[0], text):
            d, m, y = match.groups()
            try:
                dt = datetime(int(y), int(m), int(d))
                found_dates.add(dt.strftime("%Y-%m-%d"))
            except ValueError:
                pass

        # yyyy-mm-dd
        for match in re.finditer(self.DATE_PATTERNS[1], text):
            y, m, d = match.groups()
            try:
                dt = datetime(int(y), int(m), int(d))
                found_dates.add(dt.strftime("%Y-%m-%d"))
            except ValueError:
                pass

        return sorted(list(found_dates))

    def extract_currencies(self, text: str) -> list[dict[str, Any]]:
        currencies = []
        for match in self.CURRENCY_PATTERN.finditer(text):
            raw = match.group(0).strip()
            # Determine currency unit
            currency_code = "VND"
            if "$" in raw or "usd" in raw.lower():
                currency_code = "USD"
            elif "€" in raw or "eur" in raw.lower():
                currency_code = "EUR"

            # Parse numerical amount
            # Remove currency symbols and letters
            numeric_str = re.sub(r"[^\d,.]", "", raw)
            if not numeric_str:
                continue

            # Standardize thousand separators
            # If comma is thousand separator (e.g. 250,000,000 or 10,500.00)
            if "," in numeric_str and "." in numeric_str:
                if numeric_str.rfind(",") < numeric_str.rfind("."):
                    clean_str = numeric_str.replace(",", "")
                else:
                    clean_str = numeric_str.replace(".", "").replace(",", ".")
            elif "," in numeric_str:
                parts = numeric_str.split(",")
                if len(parts[-1]) == 3:  # Thousand separator: 250,000
                    clean_str = numeric_str.replace(",", "")
                else:  # Decimal: 10,5
                    clean_str = numeric_str.replace(",", ".")
            elif "." in numeric_str:
                parts = numeric_str.split(".")
                if len(parts[-1]) == 3:  # Thousand separator: 250.000
                    clean_str = numeric_str.replace(".", "")
                else:
                    clean_str = numeric_str
            else:
                clean_str = numeric_str

            try:
                val = float(clean_str)
                currencies.append({"raw": raw, "amount": val, "currency": currency_code})
            except ValueError:
                pass

        return currencies

    def extract_key_values(self, text: str) -> dict[str, str]:
        kvps = {}
        for line in text.splitlines():
            line_str = line.strip()
            if ":" in line_str or "：" in line_str:
                match = self.KVP_PATTERN.match(line_str)
                if match:
                    k, v = match.group(1).strip(), match.group(2).strip()
                    if len(k) > 1 and len(v) > 0 and len(k.split()) <= 6:
                        kvps[k] = v
        return kvps

    def extract(self, text: str) -> ExtractedEntities:
        """Executes all extraction algorithms across the input document text."""
        return ExtractedEntities(
            dates=self.extract_dates(text),
            currencies=self.extract_currencies(text),
            tax_ids=sorted(list(set(self.TAX_ID_PATTERN.findall(text)))),
            emails=sorted(list(set(self.EMAIL_PATTERN.findall(text)))),
            phone_numbers=sorted(list(set(self.PHONE_PATTERN.findall(text)))),
            key_values=self.extract_key_values(text),
        )

