"""Fix upstream letta letta-server bug: custom python tool fails with NameError: name 'DynamicModel' is not defined.

Root cause: when tool.args_json_schema lacks a 'title' field, both
  - letta/functions/helpers.py:220  generate_model_from_args_json_schema()  -> defaults model name to "DynamicModel"
  - letta/services/helpers/tool_execution_helper.py:195  add_imports_and_pydantic_schemas_for_args()  -> generates class named "DynamicModel"
create a model class literally named "DynamicModel". The sandbox injects `args_object = DynamicModel(**kwargs)` but never imports the class definition into the sandbox namespace — so the call raises NameError.

Fix: derive a deterministic, unique class name from the schema content (hash) when title is missing, and inject that title into the schema before parsing in both call sites so they agree on the same name.

Usage:
  python3 fix-tool-args-schema.py              # patches /app/letta/...
  python3 fix-tool-args-schema.py <base_dir>   # patches <base_dir>/letta/...

Idempotent: exits 0 if already patched.
"""
import sys
import hashlib
import json as _json
from pathlib import Path


def _default_model_name(schema: dict) -> str:
    """Deterministic unique class name from schema content.

    datamodel_code_generator strips underscores and other non-identifier
    chars from class names, so we must use a name that survives that strip
    unchanged in BOTH helpers.py (Pydantic create_model) and
    tool_execution_helper.py (JsonSchemaParser).
    """
    serialized = _json.dumps(schema, sort_keys=True, default=str)
    return "DynamicModel" + hashlib.md5(serialized.encode()).hexdigest()[:8]


def _helpers_default_name_and_func(text: str) -> str:
    """Inject _default_model_name helper + use it in generate_model_from_args_json_schema."""
    if "_default_model_name" in text and '_title = schema.get("title") or _default_model_name(schema)' in text:
        return text  # already patched
    # 1. Replace the default-name line
    OLD_LINE = '    return _create_model_from_schema(schema.get("title", "DynamicModel"), schema, nested_models)'
    NEW_LINES = (
        '    # PATCH (letta-secretary): unique default name when schema has no title\n'
        '    # (avoids "DynamicModel" collision across multiple tools in same sandbox)\n'
        '    _title = schema.get("title") or _default_model_name(schema)\n'
        '    return _create_model_from_schema(_title, schema, nested_models)'
    )
    if OLD_LINE not in text:
        raise SystemExit("ERROR: helpers.py: anchor for default name not found")
    text = text.replace(OLD_LINE, NEW_LINES, 1)
    # 2. Inject _default_model_name helper before generate_model_from_args_json_schema
    text = text.replace(
        "def generate_model_from_args_json_schema(",
        (
            "def _default_model_name(schema):\n"
            '    """Deterministic unique class name from schema content (letta-secretary patch)."""\n'
            "    import hashlib as _hl\n"
            "    import json as _jn\n"
            '    return "DynamicModel" + _hl.md5(_jn.dumps(schema, sort_keys=True, default=str).encode()).hexdigest()[:8]\n\n\n'
            "def generate_model_from_args_json_schema("
        ),
        1,
    )
    return text


def _teh_inject_title(text: str) -> str:
    """Inject title into args_json_schema before parsing in add_imports_and_pydantic_schemas_for_args."""
    if 'args_json_schema = {**args_json_schema, "title":' in text:
        return text  # already patched
    OLD = (
        "def add_imports_and_pydantic_schemas_for_args(args_json_schema: dict) -> str:\n"
        "    data_model_types = get_data_model_types(DataModelType.PydanticV2BaseModel, target_python_version=PythonVersion.PY_311)"
    )
    NEW = (
        "def add_imports_and_pydantic_schemas_for_args(args_json_schema: dict) -> str:\n"
        "    # PATCH (letta-secretary): inject title if missing so generated class name\n"
        "    # matches generate_model_from_args_json_schema(). Otherwise sandbox injects\n"
        "    # `args_object = DynamicModel(**kwargs)` but class is never imported -> NameError.\n"
        "    if \"title\" not in args_json_schema:\n"
        "        import hashlib as _hl\n"
        "        import json as _jn\n"
        "        _serialized = _jn.dumps(args_json_schema, sort_keys=True, default=str)\n"
        '        args_json_schema = {**args_json_schema, "title": "DynamicModel" + _hl.md5(_serialized.encode()).hexdigest()[:8]}\n'
        "    data_model_types = get_data_model_types(DataModelType.PydanticV2BaseModel, target_python_version=PythonVersion.PY_311)"
    )
    if OLD not in text:
        raise SystemExit("ERROR: tool_execution_helper.py: anchor for add_imports_and_pydantic_schemas_for_args not found")
    return text.replace(OLD, NEW, 1)


def main():
    base = Path(sys.argv[1] if len(sys.argv) > 1 else "/app")
    helpers_path = base / "letta" / "functions" / "helpers.py"
    teh_path = base / "letta" / "services" / "helpers" / "tool_execution_helper.py"

    if not helpers_path.exists():
        raise SystemExit(f"ERROR: {helpers_path} not found")
    if not teh_path.exists():
        raise SystemExit(f"ERROR: {teh_path} not found")

    helpers = helpers_path.read_text()
    helpers_new = _helpers_default_name_and_func(helpers)
    if helpers_new != helpers:
        helpers_path.write_text(helpers_new)
        print(f"OK: {helpers_path} patched")
    else:
        print(f"OK: {helpers_path} already patched")

    teh = teh_path.read_text()
    teh_new = _teh_inject_title(teh)
    if teh_new != teh:
        teh_path.write_text(teh_new)
        print(f"OK: {teh_path} patched")
    else:
        print(f"OK: {teh_path} already patched")

    print("OK: fix-tool-args-schema patch applied")


if __name__ == "__main__":
    main()
