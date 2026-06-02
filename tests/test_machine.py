import logging

import pytest

from machine import main


@pytest.mark.golden_test("golden/machine/**/*.yml")
def test_machine_golden(golden, caplog, tmp_path):
    bin_file = tmp_path / "out.maibinbin"
    config_file = tmp_path / "config.yaml"

    bin_file.write_bytes(bytes(golden["bin_file"]))
    config_file.write_text(golden["config_file"])

    with caplog.at_level(logging.INFO):
        main(str(bin_file), str(config_file))

    actual = "\n".join(record.getMessage() for record in caplog.records) + "\n"
    assert actual == golden.out["machine_log"]
