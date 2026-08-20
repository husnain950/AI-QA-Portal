from filter_deploy_env import HOST_PATH_KEYS, filter_deploy_env, main


def test_strips_host_path_keys_and_keeps_secrets():
    src = """# local paths
DATABASE_URL=postgresql+psycopg://crx:crx@127.0.0.1:5432/crx
INSECURE_COOKIES=1
UPLOAD_DIR=./data/uploads
CORPUS_ORDINANCE=./data/corpora/ordinance
CORPUS_ACTS=./data/corpora/acts
export SEED_CORPUS_ORDINANCE=/tmp/seed
OCR_CACHE_DIR=./data/ocr_cache

OPENPATHS_API_KEY=secret
OPENPATHS_BASE_URL=https://openpaths.io/v1
NORTHFLANK_PROJECT_ID=qa-pdf-portal
"""
    out = filter_deploy_env(src)
    for key in HOST_PATH_KEYS:
        assert f"{key}=" not in out
    assert "OPENPATHS_API_KEY=secret" in out
    assert "OPENPATHS_BASE_URL=https://openpaths.io/v1" in out
    assert "NORTHFLANK_PROJECT_ID=qa-pdf-portal" in out
    assert "# local paths" in out


def test_empty_input_stays_empty():
    assert filter_deploy_env("") == ""


def test_cli_writes_filtered_file(tmp_path):
    src = tmp_path / ".env"
    dest = tmp_path / "filtered.env"
    src.write_text("CORPUS_ORDINANCE=./x\nOPENPATHS_API_KEY=k\n", encoding="utf-8")
    assert main([str(src), str(dest)]) == 0
    assert dest.read_text(encoding="utf-8") == "OPENPATHS_API_KEY=k\n"
