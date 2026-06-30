"""Tests for codes.schema validation and codes.loader merge/listing logic."""
import json

import pytest

from custom_components.tuya_ir_ac.codes.loader import (
    CODES_DIR,
    get_merged_table,
    list_variants,
    load_builtin_codeset,
)
from custom_components.tuya_ir_ac.codes.schema import (
    CodeTableValidationError,
    validate_code_table,
)

VALID_TABLE = {
    "brand": "panasonic",
    "variant": "test",
    "protocol": "state",
    "codes": {
        "off": "AAAA",
        "cool_24_auto_off": "BBBB",
    },
}


def test_validate_minimal_valid_table():
    table = validate_code_table(VALID_TABLE, source="inline")
    assert table.brand == "panasonic"
    assert table.codes == {"off": "AAAA", "cool_24_auto_off": "BBBB"}
    # defaults applied
    assert table.min_temp == 16
    assert table.max_temp == 30
    assert table.fan_modes == ["auto", "low", "medium", "high"]


def test_validate_missing_required_field():
    bad = {k: v for k, v in VALID_TABLE.items() if k != "protocol"}
    with pytest.raises(CodeTableValidationError, match="protocol"):
        validate_code_table(bad, source="inline")


def test_validate_requires_off_key():
    bad = {**VALID_TABLE, "codes": {"cool_24_auto_off": "BBBB"}}
    with pytest.raises(CodeTableValidationError, match="off"):
        validate_code_table(bad, source="inline")


def test_validate_rejects_empty_codes():
    bad = {**VALID_TABLE, "codes": {}}
    with pytest.raises(CodeTableValidationError):
        validate_code_table(bad, source="inline")


def test_validate_rejects_unsupported_protocol():
    bad = {**VALID_TABLE, "protocol": "toggle"}
    with pytest.raises(CodeTableValidationError, match="protocol"):
        validate_code_table(bad, source="inline")


def test_validate_rejects_non_string_code_value():
    bad = {**VALID_TABLE, "codes": {"off": "AAAA", "cool_24_auto_off": 123}}
    with pytest.raises(CodeTableValidationError):
        validate_code_table(bad, source="inline")


def test_get_merged_table_learned_overrides_builtin():
    table = validate_code_table(VALID_TABLE, source="inline")
    merged = get_merged_table(table, {"cool_24_auto_off": "LEARNED", "heat_22_auto_off": "NEW"})
    assert merged["cool_24_auto_off"] == "LEARNED"  # overridden
    assert merged["off"] == "AAAA"  # untouched
    assert merged["heat_22_auto_off"] == "NEW"  # added


def test_get_merged_table_no_learned_codes():
    table = validate_code_table(VALID_TABLE, source="inline")
    assert get_merged_table(table, {}) == table.codes


def test_list_variants_for_brand_with_files(tmp_path, monkeypatch):
    brand_dir = tmp_path / "somebrand"
    brand_dir.mkdir()
    (brand_dir / "generic.json").write_text("{}")
    (brand_dir / "variant_a.json").write_text("{}")
    monkeypatch.setattr("custom_components.tuya_ir_ac.codes.loader.CODES_DIR", tmp_path)
    assert list_variants("somebrand") == ["generic", "variant_a"]


def test_list_variants_unknown_brand_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("custom_components.tuya_ir_ac.codes.loader.CODES_DIR", tmp_path)
    assert list_variants("does_not_exist") == []


def test_load_builtin_codeset_round_trip(tmp_path, monkeypatch):
    brand_dir = tmp_path / "panasonic"
    brand_dir.mkdir()
    (brand_dir / "generic.json").write_text(json.dumps(VALID_TABLE))
    monkeypatch.setattr("custom_components.tuya_ir_ac.codes.loader.CODES_DIR", tmp_path)
    table = load_builtin_codeset("panasonic", "generic")
    assert table.brand == "panasonic"
    assert table.codes["off"] == "AAAA"


def test_load_builtin_codeset_missing_file_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("custom_components.tuya_ir_ac.codes.loader.CODES_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        load_builtin_codeset("panasonic", "nonexistent")


def test_all_bundled_code_tables_are_valid():
    """Every JSON file actually shipped under codes/<brand>/ must validate."""
    found_any = False
    for brand_dir in CODES_DIR.iterdir():
        if not brand_dir.is_dir() or brand_dir.name.startswith("__"):
            continue
        for variant in list_variants(brand_dir.name):
            found_any = True
            table = load_builtin_codeset(brand_dir.name, variant)
            assert table.brand == brand_dir.name
            assert table.variant == variant
    # Not a hard requirement yet (built-in content is populated in a later
    # phase), but once files exist this guards their correctness.
    assert found_any or not any(CODES_DIR.glob("*/*.json"))
