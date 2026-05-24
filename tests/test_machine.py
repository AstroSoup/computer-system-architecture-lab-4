import logging
from pathlib import Path

import pytest

from machine import main

GOLDEN_DIR = Path(__file__).parent / "golden" / "machine"


def get_test_cases():
    return [d for d in GOLDEN_DIR.iterdir() if d.is_dir()]


@pytest.mark.parametrize("case_dir", get_test_cases(), ids=lambda d: d.name)
def test_machine_golden(case_dir, caplog):
    bin_file = case_dir / "out.maibinbin"
    config_file = case_dir / "config.yaml"
    expected_log_file = case_dir / "machine.log"

    with caplog.at_level(logging.INFO):
        main(str(bin_file), str(config_file))

    actual = "\n".join(record.getMessage() for record in caplog.records) + "\n"

    assert actual == expected_log_file.read_text()
