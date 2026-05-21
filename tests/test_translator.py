from pathlib import Path

import pytest

from translator import main

GOLDEN_DIR = Path(__file__).parent / "golden" / "translator"


def get_test_cases():
    return [d for d in GOLDEN_DIR.iterdir() if d.is_dir()]


@pytest.mark.parametrize("case_dir", get_test_cases(), ids=lambda d: d.name)
def test_translator_golden(case_dir, tmp_path):
    input_file = case_dir / "sources.s"
    expected_file = case_dir / "out.maibinbin"
    output_file = tmp_path / "out.maibinbin"
    expected_debug_file = case_dir / "translator.debug"
    output_debug_file = tmp_path / "translator.debug"
    main(str(input_file), str(output_file), str(output_debug_file))

    assert output_file.read_bytes() == expected_file.read_bytes()
    assert output_debug_file.read_text() == expected_debug_file.read_text()
