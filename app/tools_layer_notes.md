# Säde v1 - työkalukerros v1

Lisätyt tiedostot:

- `app/tools.py`
- päivitetty `app/main.py`

## Uudet endpointit

- `GET /tools/status`
- `GET /tools/list`
- `GET /tools/project-status`
- `POST /tools/files/list`
- `POST /tools/files/read`
- `POST /tools/files/write`
- `POST /tools/files/append`

## Turvallisuusrajat

Työkalukerros toimii vain projektikansion sisällä.

Estetyt kansiot:

- `.git`
- `.venv`, `venv`, `env`
- `__pycache__`
- `node_modules`
- `vector_db`

Sallitut tekstitiedostotyypit:

- `.py`, `.html`, `.md`, `.txt`, `.json`, `.css`, `.js`
- `.yml`, `.yaml`, `.toml`, `.ini`, `.ps1`, `.bat`

`write_file` ei ylikirjoita olemassa olevaa tiedostoa, ellei `overwrite=true`.

## Testi Swaggerissa

Avaa:

`http://127.0.0.1:8008/docs`

Kokeile:

`GET /tools/status`

Sen jälkeen:

`POST /tools/files/list`

Body:

```json
{
  "relative_path": "",
  "max_items": 50,
  "include_hidden": false
}
```

Tiedoston lukutesti:

`POST /tools/files/read`

Body:

```json
{
  "relative_path": "system_prompt.md",
  "max_chars": 5000
}
```
