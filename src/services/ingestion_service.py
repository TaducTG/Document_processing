import io
import json
import re
import uuid
from typing import Any, BinaryIO
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.exceptions import InvalidFileFormatException
from src.core.logging import logger
from src.domain.interfaces.storage import StorageService
from src.infrastructure.db.models import Document, DocumentStatus, ProcessingJob

try:
    from src.etl.parsers.complex_pdf_parser import ComplexPDFParser
except ImportError:
    ComplexPDFParser = None

ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf", ".docx"}


class IngestionService:
    """Service handling document validation, storage staging, and metadata persistence."""

    def __init__(self, db: AsyncSession, storage: StorageService):
        self.db = db
        self.storage = storage
        self.settings = get_settings()

    def validate_filename(self, filename: str) -> str:
        """Validates file extension against allowed types."""
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise InvalidFileFormatException(
                f"File extension '{ext}' is not supported. Allowed formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )
        return ext

    def parse_markdown_metadata(self, content: bytes) -> dict[str, Any]:
        """Extracts structured metadata directly from Markdown content."""
        text = content.decode("utf-8", errors="replace")
        lines = text.splitlines()

        headings = []
        title = "Untitled Document"
        for line in lines:
            line_strip = line.strip()
            if line_strip.startswith("#"):
                match = re.match(r"^(#+)\s*(.*)", line_strip)
                if match:
                    level = len(match.group(1))
                    heading_text = match.group(2).strip()
                    headings.append({"level": level, "text": heading_text})
                    if title == "Untitled Document" and level == 1:
                        title = heading_text

        words = re.findall(r"\b\w+\b", text)
        return {
            "title": title,
            "line_count": len(lines),
            "word_count": len(words),
            "char_count": len(text),
            "headings": headings,
            "has_code_blocks": "```" in text,
        }

    async def ingest_file(
        self,
        file_obj: BinaryIO,
        filename: str,
        mime_type: str = "text/markdown",
    ) -> Document:
        """Ingests, stores, and registers a document into the platform."""
        ext = self.validate_filename(filename)

        # Read content bytes
        content = file_obj.read()
        file_size = len(content)

        doc_id = str(uuid.uuid4())
        safe_filename = f"{doc_id}_{filename}"

        # 1. Upload to Object Storage
        stream = io.BytesIO(content)
        storage_path = self.storage.upload_file(
            file_obj=stream,
            object_name=safe_filename,
            bucket_name=self.settings.S3_BUCKET_RAW,
            content_type=mime_type,
        )

        # 2. Extract metadata according to file type
        doc_metadata: dict[str, Any] = {}
        extracted_text = None
        status = DocumentStatus.PENDING

        if ext in {".md", ".txt"}:
            doc_metadata = self.parse_markdown_metadata(content)
            extracted_text = content.decode("utf-8", errors="replace")
            status = DocumentStatus.COMPLETED
        elif ext == ".pdf":
            if ComplexPDFParser is not None:
                try:
                    pdf_parser = ComplexPDFParser()
                    parsed = pdf_parser.parse(content)
                    extracted_text = parsed.extracted_text
                    doc_metadata = {
                        "title": parsed.title,
                        "page_count": parsed.page_count,
                        "word_count": parsed.word_count,
                        "char_count": parsed.char_count,
                        "has_tables": parsed.has_tables,
                        "tables": parsed.tables,
                        "entities": parsed.entities.model_dump(),
                        "confidence_score": parsed.confidence_score,
                        "format": "PDF",
                    }
                    status = DocumentStatus.COMPLETED
                except Exception as e:
                    # If complex parsing fails, fall back gracefully to PENDING
                    doc_metadata = {"error": f"PDF parsing error: {str(e)}", "format": "PDF"}
                    status = DocumentStatus.PENDING
            else:
                doc_metadata = {"format": "PDF"}
                status = DocumentStatus.PENDING

        # 3. If processing succeeded, export structured artifact to processed-output S3 bucket
        if status == DocumentStatus.COMPLETED:
            try:
                output_payload = {
                    "document_id": doc_id,
                    "filename": filename,
                    "mime_type": mime_type,
                    "file_size_bytes": file_size,
                    "metadata": doc_metadata,
                    "extracted_text": extracted_text,
                }
                json_bytes = json.dumps(output_payload, ensure_ascii=False, indent=2).encode("utf-8")
                output_name = f"{doc_id}_extracted.json"
                processed_storage_path = self.storage.upload_file(
                    file_obj=io.BytesIO(json_bytes),
                    object_name=output_name,
                    bucket_name=self.settings.S3_BUCKET_PROCESSED,
                    content_type="application/json",
                )
                doc_metadata["processed_output_path"] = processed_storage_path
            except Exception as e:
                logger.warning(f"Could not export processed artifact to {self.settings.S3_BUCKET_PROCESSED}: {e}")

        # 4. Persist record in PostgreSQL
        document = Document(
            id=doc_id,
            filename=filename,
            file_size_bytes=file_size,
            mime_type=mime_type,
            storage_path=storage_path,
            status=status,
            doc_metadata=doc_metadata,
            extracted_text=extracted_text,
        )
        self.db.add(document)

        # Create Initial Processing Job
        job = ProcessingJob(
            id=str(uuid.uuid4()),
            document_id=doc_id,
            step="COMPLETED" if status == DocumentStatus.COMPLETED else "QUEUED",
            retry_count=0,
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(document)

        return document

