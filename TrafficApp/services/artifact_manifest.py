"""Resolve and atomically promote versioned model/schema artifact pairs."""
import json
import joblib
import os
import shutil
import tempfile
from pathlib import Path


MANIFEST_NAME = "current.json"


def _validate_candidate(model_path, schema_path, version):
    """Validate the release pair before writing or switching the active pointer."""
    model_path = Path(model_path)
    schema_path = Path(schema_path)
    if not model_path.is_file() or model_path.stat().st_size == 0:
        raise ValueError("Candidate model artifact is missing or empty")
    try:
        with schema_path.open(encoding="utf-8") as schema_file:
            schema = json.load(schema_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Candidate feature schema is missing or invalid") from exc
    if not isinstance(schema, dict) or schema.get("version") != version:
        raise ValueError("Candidate schema version does not match release version")
    if schema.get("model_type") != "lightgbm-binary":
        raise ValueError("Candidate schema model type is not supported")
    route_vocab = schema.get("route_vocab")
    feature_columns = schema.get("feature_columns")
    if not isinstance(route_vocab, list) or not all(isinstance(route, str) for route in route_vocab):
        raise ValueError("Candidate schema route vocabulary is invalid")
    if not isinstance(feature_columns, list) or not all(isinstance(col, str) for col in feature_columns):
        raise ValueError("Candidate schema feature columns are invalid")
    from traffic_context.ml_features import feature_columns as expected_feature_columns
    if feature_columns != expected_feature_columns(route_vocab):
        raise ValueError("Candidate schema feature columns do not match its route vocabulary")
    try:
        model = joblib.load(model_path)
        model_columns = list(model.feature_name())
    except Exception as exc:
        raise ValueError("Candidate model artifact is invalid") from exc
    if model_columns != feature_columns:
        raise ValueError("Candidate model features do not match its feature schema")
    return schema


def resolve_artifact_paths(base_dir):
    """Return model path, schema path, and release version (or legacy ``None``)."""
    base_dir = Path(base_dir)
    artifacts_dir = base_dir / "ml_artifacts"
    manifest_path = artifacts_dir / MANIFEST_NAME
    if not manifest_path.exists():
        return base_dir / "traffic_model.pkl", base_dir / "feature_schema.json", None

    with manifest_path.open(encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)

    version = manifest.get("version")
    artifact_dir = Path(manifest.get("artifact_dir", ""))
    if (
        not version
        or artifact_dir.is_absolute()
        or artifact_dir.parts != ("releases", version)
    ):
        raise ValueError("Invalid model artifact manifest")

    release_dir = (artifacts_dir / artifact_dir).resolve()
    releases_root = (artifacts_dir / "releases").resolve()
    if not release_dir.is_relative_to(releases_root):
        raise ValueError("Model artifact release escapes its release directory")
    return release_dir / "traffic_model.pkl", release_dir / "feature_schema.json", version


def promote_artifact_release(base_dir, candidate_model, candidate_schema, version):
    """Publish a complete release, then atomically switch the manifest pointer."""
    if not isinstance(version, str) or not version or Path(version).name != version or version in {".", ".."}:
        raise ValueError("Invalid model release version")
    candidate_model = Path(candidate_model)
    candidate_schema = Path(candidate_schema)
    _validate_candidate(candidate_model, candidate_schema, version)

    artifacts_dir = Path(base_dir) / "ml_artifacts"
    releases_dir = artifacts_dir / "releases"
    releases_dir.mkdir(parents=True, exist_ok=True)
    release_dir = releases_dir / version
    if release_dir.exists():
        raise FileExistsError(f"Model release already exists: {version}")

    staging_dir = Path(tempfile.mkdtemp(prefix=f".{version}-", dir=releases_dir))
    manifest_tmp = None
    try:
        shutil.copy2(candidate_model, staging_dir / "traffic_model.pkl")
        shutil.copy2(candidate_schema, staging_dir / "feature_schema.json")
        os.replace(staging_dir, release_dir)

        descriptor, manifest_tmp = tempfile.mkstemp(
            prefix=".current-", suffix=".json", dir=artifacts_dir
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as manifest_file:
            json.dump({"version": version, "artifact_dir": f"releases/{version}"}, manifest_file)
            manifest_file.write("\n")
            manifest_file.flush()
            os.fsync(manifest_file.fileno())
        os.replace(manifest_tmp, artifacts_dir / MANIFEST_NAME)
        manifest_tmp = None
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        if manifest_tmp and os.path.exists(manifest_tmp):
            os.unlink(manifest_tmp)

    return release_dir
