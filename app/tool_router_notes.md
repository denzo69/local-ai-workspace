# Säde v1 - Tool Router v1

Tämä lisää ensimmäisen automaattisen työkalureitittimen.

## Uudet tiedostot

- `app/tool_router.py`
- päivitetty `app/main.py`

## Mitä se tekee?

Chat osaa nyt tunnistaa selkeitä pyyntöjä ja käyttää työkaluja ilman Swaggeria.

Esimerkkejä chatissa:

```text
listaa tiedostot
```

```text
lue tiedosto system_prompt.md
```

```text
hae muistista veneen evä
```

```text
luo tiedosto memory/router_test.md: Tämä syntyi chatin kautta.
```

```text
lisää tiedostoon memory/router_test.md: Tämä lisättiin myöhemmin.
```

```text
työkalujen tila
```

```text
projektin tila
```

## Uudet endpointit

- `POST /tools/router/preview`
- `POST /tools/router/run`

## Turvallisuus

Router käyttää vain aiemmin rakennettua turvallista työkalukerrosta.

Se ei:
- aja komentorivikomentoja
- mene projektikansion ulkopuolelle
- käsittele estettyjä kansioita kuten `.git`, `venv`, `vector_db`
- ylikirjoita tiedostoja ilman selkeää ylikirjoituspyyntöä

## Testaus

1. Käynnistä palvelin:

```powershell
cd C:\Sade\Sade-v1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8008
```

2. Avaa UI:

```text
http://127.0.0.1:8008/ui
```

3. Kirjoita chattiin:

```text
listaa tiedostot
```

4. Kirjoita chattiin:

```text
lue tiedosto system_prompt.md
```

5. Kirjoita chattiin:

```text
hae muistista veneen evä
```
