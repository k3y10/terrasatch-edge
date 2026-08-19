from terrasatch_edge.config import load_config


def test_speech_environment_overrides(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TERRASATCH_EDGE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("TERRASATCH_EDGE_SPEECH_MODEL", "small.en")
    monkeypatch.setenv("TERRASATCH_EDGE_SPEECH_LOCAL_FILES_ONLY", "true")
    config = load_config()
    assert config.speech_model == "small.en"
    assert config.speech_compute_type == "int8"
    assert config.speech_local_files_only is True
