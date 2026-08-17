from pathlib import Path

from backend.services.corpus_sync import corpus_root_configured


def test_empty_dir_is_not_configured(tmp_path: Path):
    placeholder = tmp_path / "ordinance"
    placeholder.mkdir()
    assert corpus_root_configured(placeholder) is False


def test_dir_without_json_is_not_configured(tmp_path: Path):
    root = tmp_path / "acts"
    (root / "output").mkdir(parents=True)
    assert corpus_root_configured(root) is False


def test_pipeline_output_json_is_configured(tmp_path: Path):
    root = tmp_path / "ordinance"
    output = root / "output"
    output.mkdir(parents=True)
    (output / "ito.json").write_text("{}", encoding="utf-8")
    assert corpus_root_configured(root) is True


def test_missing_path_is_not_configured(tmp_path: Path):
    assert corpus_root_configured(tmp_path / "nope") is False
