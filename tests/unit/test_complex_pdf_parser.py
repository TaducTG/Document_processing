import io
import pytest
import pymupdf


def create_synthetic_pdf() -> bytes:
    """Generates a multi-page PDF in memory containing structured text and a table."""
    doc = pymupdf.open()
    # Page 1: Contract Header & KVPs
    page1 = doc.new_page()
    page1.insert_text(
        (50, 72),
        "ENTERPRISE SERVICE AGREEMENT CONTRACT\n\n"
        "Contract No: HD-2026/VIP-01\n"
        "Issue Date: 01/11/2026\n"
        "Tax ID: 0109998888\n"
        "Email: legal@enterprise.com\n\n"
        "Total Amount: 150,000,000 VND",
        fontsize=11,
    )

    # Page 2: Table items
    page2 = doc.new_page()
    page2.insert_text((50, 72), "APPENDIX: HARDWARE ITEMS SPECIFICATION\n", fontsize=12)

    # Draw a table with bounding lines
    page2.draw_line((50, 100), (350, 100))
    page2.draw_line((50, 130), (350, 130))
    page2.draw_line((50, 160), (350, 160))

    page2.draw_line((50, 100), (50, 160))
    page2.draw_line((150, 100), (150, 160))
    page2.draw_line((250, 100), (250, 160))
    page2.draw_line((350, 100), (350, 160))

    # Cell texts
    page2.insert_text((60, 120), "Item", fontsize=10)
    page2.insert_text((160, 120), "Description", fontsize=10)
    page2.insert_text((260, 120), "Price", fontsize=10)

    page2.insert_text((60, 150), "1", fontsize=10)
    page2.insert_text((160, 150), "Dell Server R750", fontsize=10)
    page2.insert_text((260, 150), "150,000,000", fontsize=10)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_complex_pdf_parser_extracts_text_entities_and_tables():
    from src.etl.parsers.complex_pdf_parser import ComplexPDFParser

    pdf_bytes = create_synthetic_pdf()
    parser = ComplexPDFParser()
    result = parser.parse(pdf_bytes)

    # Page and Text checks
    assert result.page_count == 2
    assert result.word_count > 10
    assert "ENTERPRISE SERVICE AGREEMENT CONTRACT" in result.extracted_text

    # Entities
    assert "0109998888" in result.entities.tax_ids
    assert "2026-11-01" in result.entities.dates
    assert any(c["amount"] == 150000000.0 for c in result.entities.currencies)
    assert result.entities.key_values.get("Contract No") == "HD-2026/VIP-01"
    assert "legal@enterprise.com" in result.entities.emails

    # Tables
    assert len(result.tables) >= 1
    table = result.tables[0]
    assert table["page"] == 2
    assert "headers" in table
    assert len(table["rows"]) >= 1

    # Confidence score
    assert result.confidence_score >= 0.80
