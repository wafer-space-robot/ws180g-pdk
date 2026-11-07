<!-- SPDX-License-Identifier: Apache-2.0 -->
# onsemi ONC18 data sheet (`onc18`)

The onsemi ONC18 0.18 µm process data sheet `ONC181818/D`, revision 0 (2016), is
registered in `evidence/data/sources.toml` but **not yet transcribed**: it has no entries,
`retrieved` is absent and `transcribed = false`.

- **URL:** <https://www.onsemi.com/site/pdf/ONC181818-D.PDF>
- **Licence:** not redistributed; only facts with page citations will be recorded.

## Why it is pending

The automated download was refused by the site: it returns an HTML page instead of the
PDF to non-browser clients. A person must download the PDF with a browser into
`tmp/ref/onsemi/` (gitignored).

## To transcribe it

1. Download the PDF into `tmp/ref/onsemi/ONC181818-D.PDF`.
2. Record its sha256 under `[sources.onc18.sha256]` and the download date as `retrieved`.
3. Transcribe the "Process Characteristics" values into `evidence/data/onc18.toml`, in the
   form of `evidence/data/xc018.toml`, each with its page in `cite`.
4. Set `transcribed = true` and list the pages here.
