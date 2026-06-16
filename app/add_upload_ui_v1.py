from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import re
import py_compile


def backup_file(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup = path.with_name(f"{path.stem}_backup_upload_ui_{timestamp}{path.suffix}")
    shutil.copy2(path, backup)
    return backup


def patch_fastapi_import(text: str) -> str:
    if "from fastapi import FastAPI, HTTPException" in text and "UploadFile" not in text:
        return text.replace(
            "from fastapi import FastAPI, HTTPException",
            "from fastapi import FastAPI, HTTPException, UploadFile, File"
        )

    match = re.search(r"from fastapi import ([^\n]+)", text)
    if match:
        names = [part.strip() for part in match.group(1).split(",")]
        changed = False
        for name in ["UploadFile", "File"]:
            if name not in names:
                names.append(name)
                changed = True

        if changed:
            return text[:match.start()] + "from fastapi import " + ", ".join(names) + text[match.end():]

    return text


def patch_main(project_path: Path) -> None:
    main_path = project_path / "app" / "main.py"

    if not main_path.exists():
        raise FileNotFoundError(f"main.py ei löytynyt: {main_path}")

    backup = backup_file(main_path)
    print(f"Varmuuskopioitu main.py: {backup}")

    text = main_path.read_text(encoding="utf-8")
    original = text

    text = patch_fastapi_import(text)

    if "UPLOADS_PATH" not in text:
        marker = 'UI_TEMPLATE_PATH = TEMPLATES_PATH / "ui.html"\n'
        if marker not in text:
            raise RuntimeError("En löytänyt UI_TEMPLATE_PATH-riviä, johon UPLOADS_PATH lisätään.")

        text = text.replace(
            marker,
            marker + 'UPLOADS_PATH = PROJECT_PATH / "uploads"\n'
        )

    if "UPLOAD_ALLOWED_EXTENSIONS" not in text:
        insert_after = 'UPLOADS_PATH = PROJECT_PATH / "uploads"\n'
        if insert_after not in text:
            insert_after = 'UI_TEMPLATE_PATH = TEMPLATES_PATH / "ui.html"\n'

        upload_constants = """
UPLOAD_ALLOWED_EXTENSIONS = {
    ".txt", ".md", ".json", ".py", ".html", ".htm", ".css", ".js",
    ".yml", ".yaml", ".toml", ".ini", ".ps1", ".bat"
}
UPLOAD_MAX_BYTES = 25 * 1024 * 1024
"""
        text = text.replace(insert_after, insert_after + upload_constants)

    if "UPLOADS_PATH.mkdir" not in text:
        marker = "    TEMPLATES_PATH.mkdir(parents=True, exist_ok=True)\n"
        if marker not in text:
            raise RuntimeError("En löytänyt ensure_paths() -kohdasta TEMPLATES_PATH.mkdir-riviä.")

        text = text.replace(
            marker,
            marker + "    UPLOADS_PATH.mkdir(parents=True, exist_ok=True)\n"
        )

    if '"/files/upload"' not in text:
        if '            "/files/ingest",' in text:
            text = text.replace(
                '            "/files/ingest",',
                '            "/files/upload",\n            "/files/ingest",'
            )
        elif '            "/tools/router/run",' in text:
            text = text.replace(
                '            "/tools/router/run",',
                '            "/tools/router/run",\n            "/files/upload",'
            )

    upload_endpoint = """
@app.post("/files/upload")
async def upload_file(file: UploadFile = File(...)):
    ensure_paths()

    original_name = Path(file.filename or "").name.strip()

    if not original_name:
        raise HTTPException(status_code=400, detail="Tiedostonimi puuttuu.")

    suffix = Path(original_name).suffix.lower()

    if suffix not in UPLOAD_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Tiedostotyyppi ei ole sallittu upload v1:ssä: {suffix}"
        )

    data = await file.read()

    if not data:
        raise HTTPException(status_code=400, detail="Tiedosto on tyhjä.")

    if len(data) > UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Tiedosto on liian suuri. Maksimi on {UPLOAD_MAX_BYTES} tavua."
        )

    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Upload v1 tukee vain UTF-8-tekstitiedostoja."
        )

    target = UPLOADS_PATH / original_name

    if target.exists():
        stem = target.stem
        ext = target.suffix
        counter = 1

        while True:
            candidate = UPLOADS_PATH / f"{stem}_{counter}{ext}"
            if not candidate.exists():
                target = candidate
                break
            counter += 1

    target.write_bytes(data)

    relative_path = str(target.relative_to(PROJECT_PATH)).replace("\\\\", "/")

    result = {
        "ok": True,
        "message": "Tiedosto ladattu Säteelle.",
        "filename": target.name,
        "relative_path": relative_path,
        "path": str(target),
        "size_bytes": target.stat().st_size,
        "time": datetime.now().isoformat(timespec="seconds"),
        "next_steps": [
            f"tiivistä tiedosto {relative_path}",
            f"lisää tiedosto {relative_path} muistiin"
        ]
    }

    try:
        log_tool_event(
            PROJECT_PATH,
            tool="upload_file",
            action="api",
            request={"filename": original_name, "size_bytes": len(data)},
            result=result,
        )
    except Exception:
        pass

    return result
"""

    if '@app.post("/files/upload")' not in text:
        anchors = [
            '@app.post("/files/summarize")',
            '@app.post("/tools/router/preview")',
            '@app.get("/semantic/status")',
            '@app.get("/system-prompt")',
        ]

        inserted = False

        for anchor in anchors:
            if anchor in text:
                text = text.replace(anchor, upload_endpoint + "\n" + anchor)
                inserted = True
                break

        if not inserted:
            raise RuntimeError("En löytänyt sopivaa kohtaa /files/upload endpointille.")

    if text != original:
        compile(text, str(main_path), "exec")
        main_path.write_text(text, encoding="utf-8")
        py_compile.compile(str(main_path), doraise=True)
        print("main.py päivitetty ja syntaksitarkistus OK.")
    else:
        print("main.py ei tarvinnut muutoksia.")


def patch_ui(project_path: Path) -> None:
    ui_path = project_path / "app" / "templates" / "ui.html"

    if not ui_path.exists():
        raise FileNotFoundError(f"ui.html ei löytynyt: {ui_path}")

    backup = backup_file(ui_path)
    print(f"Varmuuskopioitu ui.html: {backup}")

    text = ui_path.read_text(encoding="utf-8")
    original = text

    upload_block = """
<!-- Säde upload UI v1 -->
<section id="sade-upload-section" style="margin-top: 32px;">
    <h2>Liitä tiedosto Säteelle</h2>

    <p style="margin-bottom: 10px;">
        Lataa tekstitiedosto uploads-kansioon. Sen jälkeen voit pyytää Sädeä tiivistämään sen tai lisäämään sen muistiin.
    </p>

    <input
        id="sade-upload-file"
        type="file"
        accept=".txt,.md,.json,.py,.html,.htm,.css,.js,.yml,.yaml,.toml,.ini,.ps1,.bat"
        style="display:block; margin-bottom: 12px;"
    />

    <button type="button" onclick="uploadFileToSade()">Lähetä tiedosto Säteelle</button>

    <pre id="sade-upload-result" style="white-space: pre-wrap; margin-top: 14px;"></pre>
</section>

<script>
async function uploadFileToSade() {
    const input = document.getElementById("sade-upload-file");
    const resultBox = document.getElementById("sade-upload-result");

    if (!input || !input.files || input.files.length === 0) {
        resultBox.textContent = "Valitse ensin tiedosto.";
        return;
    }

    const file = input.files[0];
    const formData = new FormData();
    formData.append("file", file);

    resultBox.textContent = "Lähetetään tiedostoa Säteelle...";

    try {
        const response = await fetch("/files/upload", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (!response.ok || !data.ok) {
            resultBox.textContent = "Upload epäonnistui:\\n" + JSON.stringify(data, null, 2);
            return;
        }

        resultBox.textContent =
            "Tiedosto ladattu onnistuneesti.\\n\\n" +
            "Polku: " + data.relative_path + "\\n" +
            "Koko: " + data.size_bytes + " tavua\\n\\n" +
            "Voit nyt kirjoittaa chattiin esimerkiksi:\\n" +
            "- tiivistä tiedosto " + data.relative_path + "\\n" +
            "- lisää tiedosto " + data.relative_path + " muistiin";

    } catch (error) {
        resultBox.textContent = "Upload epäonnistui: " + error;
    }
}
</script>
<!-- /Säde upload UI v1 -->
"""

    if "sade-upload-section" not in text:
        lower = text.lower()

        if "</body>" in lower:
            index = lower.rfind("</body>")
            text = text[:index] + upload_block + "\n" + text[index:]
        else:
            text = text + "\n" + upload_block + "\n"

    if text != original:
        ui_path.write_text(text, encoding="utf-8")
        print("ui.html päivitetty.")
    else:
        print("ui.html ei tarvinnut muutoksia.")


def main():
    project_path = Path.cwd().resolve()

    if not (project_path / "app").exists():
        raise RuntimeError(
            "Aja tämä projektin juuresta, esimerkiksi:\\n"
            "cd C:\\\\Sade\\\\Sade-v1\\n"
            "python C:\\\\Sade\\\\add_upload_ui_v1.py"
        )

    print(f"Projektikansio: {project_path}")

    patch_main(project_path)
    patch_ui(project_path)

    print()
    print("Valmis.")
    print()
    print("TÄRKEÄÄ: varmista, että python-multipart on asennettu:")
    print("python -m pip install python-multipart")
    print()
    print("Käynnistä palvelin uudelleen:")
    print("python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8008")
    print()
    print("Avaa UI:")
    print("http://127.0.0.1:8008/ui")


if __name__ == "__main__":
    main()
