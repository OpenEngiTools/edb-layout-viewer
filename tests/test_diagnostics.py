import logging

import pytest

from viewer_adapter.diagnostics import _Diagnostics, _record_exception


def test_normal_mode_records_message_and_continues():
    diagnostics = _Diagnostics()
    error = RuntimeError("capture failed")

    _record_exception(diagnostics, "object skipped", error)

    assert diagnostics == ["object skipped"]
    assert not hasattr(error, "_viewer_diagnostics_logged")


def test_debug_mode_records_traceback_logs_and_reraises_once(caplog):
    diagnostics = _Diagnostics(debug=True)
    error = RuntimeError("capture failed")

    with caplog.at_level(logging.ERROR, logger="viewer_adapter.diagnostics"):
        try:
            raise error
        except RuntimeError as caught:
            with pytest.raises(RuntimeError, match="capture failed"):
                _record_exception(diagnostics, "object failed", caught)
            with pytest.raises(RuntimeError, match="capture failed"):
                _record_exception(diagnostics, "object failed", caught)

    assert diagnostics[0] == "object failed"
    assert "Traceback" in diagnostics[1]
    assert len(caplog.records) == 1
