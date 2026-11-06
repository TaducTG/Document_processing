import io
import re
from typing import Any
import pdfplumber
import pymupdf
from pydantic import BaseModel, Field

from src.core.logging import logger
from src.etl.extractors.entity_extractor import EntityExtractor, ExtractedEntities


class ParsedDocumentResult(BaseModel):
    """Normalized structured result of complex document processing."""

    title: str = "Untitled Document"
    page_count: int = 0
    word_count: int = 0
    char_count: int = 0
    extracted_text: str = ""
    has_tables: bool = False
    tables: list[dict[str, Any]] = Field(default_factory=list)
    entities: ExtractedEntities = Field(default_factory=ExtractedEntities)
    confidence_score: float = 1.0


class ComplexPDFParser:
    """Enterprise parser for complex PDFs: multi-column layout, table matrix, and entity harvesting."""

    def __init__(self):
        self.entity_extractor = EntityExtractor()

    def _extract_layout_aware_text(self, doc: pymupdf.Document) -> tuple[str, list[str]]:
        """Extracts text respecting spatial columns and reading order across all pages."""
        full_text_parts = []
        page_texts = []

        for page in doc:
            # get_text("blocks") returns tuples: (x0, y0, x1, y1, "text", block_no, block_type)
            blocks = page.get_text("blocks")
            # Filter text blocks (block_type == 0 is text, 1 is image)
            text_blocks = [b for b in blocks if b[6] == 0 and b[4].strip()]

            # Sort blocks: primary key is horizontal column band, secondary is vertical y0
            # To handle 2-column documents cleanly:
            page_width = page.rect.width
            mid_point = page_width / 2.0

            def sort_key(b):
                x0, y0 = b[0], b[1]
                column = 0 if x0 < mid_point else 1
                return (column, y0)

            # Check if multi-column layout is likely present
            has_right_col = any(b[0] >= mid_point for b in text_blocks)
            has_left_col = any(b[0] < mid_point for b in text_blocks)

            if has_left_col and has_right_col and len(text_blocks) > 4:
                text_blocks.sort(key=sort_key)
            else:
                text_blocks.sort(key=lambda b: (b[1], b[0]))

            page_content = "\n\n".join(b[4].strip() for b in text_blocks)
            page_texts.append(page_content)
            full_text_parts.append(page_content)

        return "\n\n--- Page Break ---\n\n".join(full_text_parts), page_texts

    def _extract_tables(self, pdf_bytes: bytes) -> list[dict[str, Any]]:
        """Uses pdfplumber to detect border matrices and tabular grids across pages."""
        extracted_tables = []
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page_idx, page in enumerate(pdf.pages, start=1):
                    tables = page.extract_tables()
                    for t_idx, raw_table in enumerate(tables):
                        if not raw_table or len(raw_table) < 2:
                            continue

                        # Clean nulls / whitespace
                        cleaned_rows = []
                        for row in raw_table:
                            cleaned_row = [str(c).strip() if c is not None else "" for c in row]
                            if any(cleaned_row):
                                cleaned_rows.append(cleaned_row)

                        if len(cleaned_rows) >= 2:
                            headers = cleaned_rows[0]
                            data_rows = cleaned_rows[1:]
                            extracted_tables.append({
                                "page": page_idx,
                                "table_index": t_idx + 1,
                                "headers": headers,
                                "rows": data_rows,
                                "row_count": len(data_rows),
                                "col_count": len(headers),
                            })
        except Exception as e:
            logger.warning(f"Table extraction encountered non-critical error: {e}")

        return extracted_tables

    def parse(self, content: bytes) -> ParsedDocumentResult:
        """Parses complex PDF bytes into fully structured JSON metadata, tables, and entities."""
        doc = pymupdf.open(stream=content, filetype="pdf")
        page_count = len(doc)

        # 1. Layout-aware text extraction
        extracted_text, _ = self._extract_layout_aware_text(doc)

        # Title heuristic
        title = doc.metadata.get("title") or ""
        if not title:
            # Use first non-empty line of text
            for line in extracted_text.splitlines():
                clean_l = line.strip()
                if len(clean_l) > 3 and not clean_l.startswith("---"):
                    title = clean_l
                    break
        if not title:
            title = "PDF Document"

        # 2. Extract structured tables
        tables = self._extract_tables(content)

        # 3. Extract business-critical entities & Key-Value pairs
        entities = self.entity_extractor.extract(extracted_text)

        # 4. Compute metrics & confidence score
        words = re.findall(r"\b\w+\b", extracted_text)
        word_count = len(words)
        char_count = len(extracted_text)

        # Confidence heuristic: penalize empty text or lack of structure
        confidence = 1.0
        if word_count < 10:
            confidence -= 0.5
        if not entities.dates and not entities.key_values:
            confidence -= 0.1
        confidence = max(0.1, min(1.0, confidence))

        doc.close()

        return ParsedDocumentResult(
            title=title,
            page_count=page_count,
            word_count=word_count,
            char_count=char_count,
            extracted_text=extracted_text,
            has_tables=len(tables) > 0,
            tables=tables,
            entities=entities,
            confidence_score=round(confidence, 2),
        )

