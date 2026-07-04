from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import ast
import hashlib
import json
import re


SAFE_EXTENSIONS = {
    ".py", ".html", ".htm", ".md", ".txt", ".json", ".css", ".js",
    ".yml", ".yaml", ".toml", ".ini", ".ps1", ".bat"
}

BLOCKED_DIR_NAMES = {
    ".git", ".venv", "venv", "env", "__pycache__", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "vector_db"
}

MAX_FILES = 1000
MAX_READ_CHARS = 300_000



def _resolve_app_path(project_path: Path) -> Path:
    """
    Dev Mode voi saada joko projektijuuren:
        <project-root>

    tai suoraan app-kansion:
        <project-root>/app

    Tämä palauttaa aina oikean app-kansion.
    """
    project_path = Path(project_path).resolve()

    if project_path.name.lower() == "app":
        return project_path

    candidate = project_path / "app"

    if candidate.exists() and candidate.is_dir():
        return candidate

    return project_path


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _memory_path(project_path: Path) -> Path:
    project_path = _resolve_app_path(project_path)
    path = project_path / "memory"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _map_path(project_path: Path) -> Path:
    project_path = _resolve_app_path(project_path)
    return _memory_path(project_path) / "codebase_map.json"


def _relative(project_path: Path, path: Path) -> str:
    project_path = _resolve_app_path(project_path)
    return str(path.resolve().relative_to(project_path.resolve())).replace("\\", "/")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _should_skip(path: Path, project_path: Path) -> bool:
    project_path = _resolve_app_path(project_path)
    try:
        relative = path.resolve().relative_to(project_path.resolve())
    except ValueError:
        return True

    for part in relative.parts:
        if part in BLOCKED_DIR_NAMES:
            return True
        if part.startswith(".") and part not in {".env"}:
            return True

    name = path.name.lower()

    if "_backup_" in name or name.endswith(".pyc"):
        return True

    if name in {"tasks.json", "tool_log.jsonl", "task_history.jsonl", "ingested_files.jsonl", "memory_log.jsonl", "chat_log.md", "sade_memory.md"}:
        return True

    return False


def _read_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if len(text) > MAX_READ_CHARS:
        return text[:MAX_READ_CHARS]
    return text


def _analyze_python(text: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "language": "python",
        "imports": [],
        "classes": [],
        "functions": [],
        "routes": [],
    }

    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        result["syntax_error"] = str(error)
        return result

    imports: List[str] = []
    classes: List[Dict[str, Any]] = []
    functions: List[Dict[str, Any]] = []
    routes: List[Dict[str, Any]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append(f"{module}.{alias.name}" if module else alias.name)

        elif isinstance(node, ast.ClassDef):
            classes.append({
                "name": node.name,
                "line": node.lineno,
                "methods": [
                    item.name for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                ],
            })

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decorators = []
            for decorator in node.decorator_list:
                try:
                    decorators.append(ast.unparse(decorator))
                except Exception:
                    decorators.append(type(decorator).__name__)

            functions.append({
                "name": node.name,
                "line": node.lineno,
                "async": isinstance(node, ast.AsyncFunctionDef),
                "decorators": decorators[:10],
            })

            for decorator in decorators:
                match = re.search(r"app\.(get|post|put|delete|patch)\((.+?)\)", decorator)
                if match:
                    route_text = match.group(2)
                    path_match = re.search(r'["\'](.+?)["\']', route_text)
                    routes.append({
                        "method": match.group(1).upper(),
                        "path": path_match.group(1) if path_match else None,
                        "function": node.name,
                        "line": node.lineno,
                    })

    result["imports"] = sorted(set(imports))[:200]
    result["classes"] = classes
    result["functions"] = functions
    result["routes"] = routes

    return result


def _analyze_html(text: str) -> Dict[str, Any]:
    ids = sorted(set(re.findall(r'id=["\']([^"\']+)["\']', text)))
    functions = sorted(set(re.findall(r"function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", text)))
    fetches = sorted(set(re.findall(r'fetch\(["\']([^"\']+)["\']', text)))

    return {
        "language": "html",
        "ids": ids[:200],
        "functions": functions[:200],
        "fetches": fetches[:200],
    }


def _analyze_json(text: str) -> Dict[str, Any]:
    try:
        data = json.loads(text)
    except Exception as error:
        return {
            "language": "json",
            "parse_error": str(error),
        }

    if isinstance(data, dict):
        keys = list(data.keys())[:100]
        shape = "object"
    elif isinstance(data, list):
        keys = []
        shape = f"array[{len(data)}]"
    else:
        keys = []
        shape = type(data).__name__

    return {
        "language": "json",
        "shape": shape,
        "top_level_keys": keys,
    }


def _analyze_markdown(text: str) -> Dict[str, Any]:
    headings = re.findall(r"^(#{1,6})\s+(.+)$", text, flags=re.MULTILINE)
    links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text)

    return {
        "language": "markdown",
        "headings": [
            {"level": len(level), "text": title.strip()}
            for level, title in headings[:100]
        ],
        "links": [
            {"text": title, "url": url}
            for title, url in links[:50]
        ],
    }


def analyze_file(project_path: Path, path: Path, include_snippet: bool = False) -> Dict[str, Any]:
    project_path = _resolve_app_path(project_path)
    text = _read_text(path)
    suffix = path.suffix.lower()
    relative = _relative(project_path, path)

    item: Dict[str, Any] = {
        "path": relative,
        "name": path.name,
        "suffix": suffix,
        "size_bytes": path.stat().st_size,
        "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        "sha256": _sha256(text),
        "line_count": len(text.splitlines()),
        "char_count": len(text),
    }

    if suffix == ".py":
        item["analysis"] = _analyze_python(text)
    elif suffix in {".html", ".htm"}:
        item["analysis"] = _analyze_html(text)
    elif suffix == ".json":
        item["analysis"] = _analyze_json(text)
    elif suffix in {".md", ".txt"}:
        item["analysis"] = _analyze_markdown(text)
    else:
        item["analysis"] = {
            "language": suffix.lstrip(".") or "text"
        }

    if include_snippet:
        item["snippet"] = text[:1200]

    return item


def read_codebase_map(project_path: Path) -> Dict[str, Any]:
    project_path = _resolve_app_path(project_path)
    path = _map_path(project_path)

    if not path.exists():
        return {
            "ok": False,
            "message": "Codebase mapia ei ole vielä luotu. Aja ensin /dev/map.",
            "map_path": str(path),
        }

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        return {
            "ok": False,
            "message": "Codebase mapia ei voitu lukea.",
            "error": str(error),
            "map_path": str(path),
        }


def find_in_codebase_map(project_path: Path, query: str, limit: int = 20) -> Dict[str, Any]:
    project_path = _resolve_app_path(project_path)
    clean_query = query.strip().lower()

    if not clean_query:
        return {
            "ok": False,
            "message": "Hakusana ei saa olla tyhjä.",
            "query": query,
            "results": [],
        }

    code_map = read_codebase_map(project_path)

    if not code_map.get("ok"):
        return {
            **code_map,
            "query": query,
            "results": [],
        }

    results: List[Dict[str, Any]] = []

    for item in code_map.get("files", []):
        haystack_parts = [
            item.get("path", ""),
            item.get("name", ""),
            item.get("suffix", ""),
        ]

        analysis = item.get("analysis") or {}
        haystack_parts.extend(analysis.get("imports", []))

        for function in analysis.get("functions", []):
            if isinstance(function, dict):
                haystack_parts.append(function.get("name", ""))
                haystack_parts.extend(function.get("decorators", []))
            else:
                haystack_parts.append(str(function))

        for class_item in analysis.get("classes", []):
            if isinstance(class_item, dict):
                haystack_parts.append(class_item.get("name", ""))
                haystack_parts.extend(class_item.get("methods", []))
            else:
                haystack_parts.append(str(class_item))

        for route in analysis.get("routes", []):
            if isinstance(route, dict):
                haystack_parts.append(route.get("path") or "")
                haystack_parts.append(route.get("function") or "")
            else:
                haystack_parts.append(str(route))

        for fetch in analysis.get("fetches", []):
            haystack_parts.append(fetch)

        haystack = " ".join(str(part).lower() for part in haystack_parts)

        if clean_query in haystack:
            results.append({
                "type": "file",
                "path": item.get("path"),
                "name": item.get("name"),
                "suffix": item.get("suffix"),
                "analysis": analysis,
            })

    return {
        "ok": True,
        "query": query,
        "count": len(results[:limit]),
        "results": results[:limit],
    }


# SAFE_BUILD_CODEBASE_MAP_V1_START
# Korvaa alkuperäisen build_codebase_map-funktion turvallisemmalla versiolla.
# Tämä sietää sen, jos analyysi palauttaa routes/functions/classes-listoihin
# joskus merkkijonoja dictien sijasta.

def _safe_mapping_item(item, file_path: str, default_key: str = "name"):
    if isinstance(item, dict):
        result = dict(item)
        result.setdefault("file", file_path)
        return result

    return {
        default_key: str(item),
        "file": file_path,
    }


def build_codebase_map(project_path: Path, include_snippets: bool = False) -> Dict[str, Any]:
    project_path = _resolve_app_path(project_path)

    files: List[Dict[str, Any]] = []
    routes: List[Dict[str, Any]] = []
    functions: List[Dict[str, Any]] = []
    classes: List[Dict[str, Any]] = []

    scanned = 0

    for path in sorted(project_path.rglob("*"), key=lambda p: str(p).lower()):
        if scanned >= MAX_FILES:
            break

        if not path.is_file():
            continue

        if path.suffix.lower() not in SAFE_EXTENSIONS:
            continue

        if _should_skip(path, project_path):
            continue

        scanned += 1

        try:
            file_info = analyze_file(project_path, path, include_snippet=include_snippets)

            if not isinstance(file_info, dict):
                file_info = {
                    "path": _relative(project_path, path),
                    "error": f"analyze_file palautti odottamattoman tyypin: {type(file_info).__name__}",
                    "analysis": {},
                }

        except Exception as error:
            file_info = {
                "path": _relative(project_path, path),
                "error": str(error),
                "analysis": {},
            }

        files.append(file_info)

        file_relative = str(file_info.get("path", _relative(project_path, path)))
        analysis = file_info.get("analysis") or {}

        if not isinstance(analysis, dict):
            analysis = {}

        for route in analysis.get("routes") or []:
            routes.append(_safe_mapping_item(route, file_relative, default_key="path"))

        for function in analysis.get("functions") or []:
            functions.append(_safe_mapping_item(function, file_relative, default_key="name"))

        for class_item in analysis.get("classes") or []:
            classes.append(_safe_mapping_item(class_item, file_relative, default_key="name"))

    result = {
        "ok": True,
        "message": "Codebase map luotu.",
        "created_at": _now(),
        "project_path": str(project_path),
        "map_path": str(_map_path(project_path)),
        "file_count": len(files),
        "route_count": len(routes),
        "function_count": len(functions),
        "class_count": len(classes),
        "files": files,
        "routes": routes,
        "functions": functions,
        "classes": classes,
        "safe_builder": "v1",
    }

    _map_path(project_path).write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return result
# SAFE_BUILD_CODEBASE_MAP_V1_END

