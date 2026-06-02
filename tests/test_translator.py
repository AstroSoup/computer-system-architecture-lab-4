import pytest

from translator import main


@pytest.mark.golden_test("golden/translator/**/*.yml")
def test_translator_golden(golden, tmp_path):
    input_file = tmp_path / "sources.s"
    output_file = tmp_path / "out.maibinbin"
    output_debug_file = tmp_path / "translator.debug"

    input_file.write_text(golden["sources"])

    main(str(input_file), str(output_file), str(output_debug_file), True)

    assert output_file.read_bytes() == bytes(golden["bin_out"])
    assert output_debug_file.read_text() == golden.out["translator_debug"]
