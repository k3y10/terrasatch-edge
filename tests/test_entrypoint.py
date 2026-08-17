from __future__ import annotations

import terrasatch_edge.entrypoint as entrypoint
from terrasatch_edge import __version__


def test_version_flag_prints_package_version(capsys) -> None:
    entrypoint.main(["--version"])

    assert capsys.readouterr().out.strip() == f"terrasatch-edge {__version__}"


def test_short_version_flag_prints_package_version(capsys) -> None:
    entrypoint.main(["-V"])

    assert capsys.readouterr().out.strip() == f"terrasatch-edge {__version__}"
