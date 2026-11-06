import pytest


def test_entity_extractor_parses_dates_currencies_and_kvps():
    from src.etl.extractors.entity_extractor import EntityExtractor

    sample_contract_text = """
    CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
    Độc lập - Tự do - Hạnh phúc

    HỢP ĐỒNG KINH TẾ
    Số hợp đồng: HD-2026/FPT-AI/09
    Ngày ký: 31/10/2026
    Thời hạn hiệu lực: 2027-10-31

    BÊN A: CÔNG TY TNHH CÔNG NGHỆ ALPHA
    Đại diện: Ông Nguyễn Văn A
    Mã số thuế: 0101234567
    Email: contact@alpha-tech.vn

    ĐIỀU 3: GIÁ TRỊ HỢP ĐỒNG VÀ PHƯƠNG THỨC THANH TOÁN
    1. Tổng giá trị hợp đồng là: 250,000,000 VNĐ (Bằng chữ: Hai trăm năm mươi triệu đồng).
    2. Đợt 1 thanh toán: $10,500 USD trước ngày 15/11/2026.
    """

    extractor = EntityExtractor()
    result = extractor.extract(sample_contract_text)

    # 1. Dates
    assert "2026-10-31" in result.dates
    assert "2027-10-31" in result.dates
    assert "2026-11-15" in result.dates

    # 2. Currencies
    amounts = [c["amount"] for c in result.currencies]
    assert 250000000.0 in amounts
    assert 10500.0 in amounts

    # 3. Tax ID & Email
    assert "0101234567" in result.tax_ids
    assert "contact@alpha-tech.vn" in result.emails

    # 4. Key-Value Pairs
    assert "Số hợp đồng" in result.key_values
    assert "HD-2026/FPT-AI/09" in result.key_values["Số hợp đồng"]
    assert "Mã số thuế" in result.key_values
    assert result.key_values["Mã số thuế"] == "0101234567"

