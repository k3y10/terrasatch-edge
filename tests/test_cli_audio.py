from click import unstyle
from typer.testing import CliRunner

from terrasatch_edge.entrypoint import app


runner = CliRunner()


def test_ingest_audio_command_is_registered() -> None:
    result = runner.invoke(app, ["ingest-audio", "--help"])
    assert result.exit_code == 0
    output = unstyle(result.output)
    assert "Transcribe local radio audio" in output
    assert "--hotwords" in output
