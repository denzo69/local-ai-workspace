# Säde v1 - Tool Log + File Ingestion v1

Tämä päivitys lisää kaksi tärkeää kerrosta:

1. Työkaluloki
2. Tiedostojen käsittely / file ingestion

## Uudet tiedostot

Kopioi nämä `app`-kansioon:

- `tool_log.py`
- `file_ingestion.py`
- `tool_router_with_ingestion.py` -> nimeä muotoon `tool_router.py`
- `main_with_file_ingestion.py` -> nimeä muotoon `main.py`

## Uudet kansiot ja lokit

Sovellus luo automaattisesti:

- `app/uploads/`
- `app/memory/tool_log.jsonl`
- `app/memory/ingested_files.jsonl`

## Uudet endpointit

- `POST /files/summarize`
- `POST /files/ingest`
- `POST /files/ingestion-log`
- `POST /tools/log`

## Chat-komennot

Nämä toimivat suoraan UI-chatissa:

```text
tiivistä tiedosto uploads/testi.md
```

```text
lisää tiedosto uploads/testi.md muistiin
```

```text
indeksoi tiedosto uploads/testi.md
```

```text
näytä työkaluloki
```

```text
näytä ingestion log
```

Aiemmat toimivat edelleen:

```text
listaa tiedostot
```

```text
lue tiedosto system_prompt.md
```

```text
hae muistista veneen evä
```

## Käyttö

1. Luo uploads-kansio, jos sitä ei vielä ole:

```powershell
cd C:\Sade\Sade-v1\app
mkdir uploads
```

2. Kopioi testitiedosto sinne, esimerkiksi:

```text
C:\Sade\Sade-v1\app\uploads\testi.md
```

3. Käynnistä palvelin:

```powershell
cd C:\Sade\Sade-v1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8008
```

4. Kirjoita UI-chatissa:

```text
tiivistä tiedosto uploads/testi.md
```

5. Kirjoita:

```text
lisää tiedosto uploads/testi.md muistiin
```

Tämä lisää tiedoston tiivistelmän `sade_memory.md`-tiedostoon ja koko sisällön semanttiseen muistiin.

## Turvallisuus

File ingestion v1 käsittelee vain turvallisia tekstitiedostoja:

- `.txt`
- `.md`
- `.json`
- `.py`
- `.html`
- `.css`
- `.js`
- `.yml`
- `.yaml`
- `.toml`
- `.ini`
- `.ps1`
- `.bat`

Ei vielä PDF-, DOCX-, Excel- tai kuvatiedostoja. Ne kannattaa lisätä myöhemmin erillisinä lukijoina.
