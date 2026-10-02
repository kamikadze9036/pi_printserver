# printserver_win reference mapping

Reference inspected read-only: `kamikadze9036/printserver_win`, branch `master`.
GitHub file blob IDs: `models.py` = `f2574b2b20cb546cd199f6db16e7bbb7a2ac0704`,
`printer.py` = `832e6a92dcc0cc5efcb86fdc87fdd50ac3c71e5e`.
The local reference checkout was also inspected; it contains an earlier version
without `highlight_right`. Neither checkout nor its database is modified.

| Reference | pi_printserver |
| --- | --- |
| SQLite `templates.name`, `width_mm`, `height_mm` | PostgreSQL templates, same units |
| JSON string `templates.elements` | Validated JSON array, text and QR elements |
| Element `x/y/w/h` | Millimetres, checked against label dimensions |
| Text `font_size` | Reference conversion: `max(20, int(font_size * dpi / 25.4 * 0.35))` |
| Product `product_code` | Unique, uppercase product code |
| `qr_content`, `text_content`, `text2`–`text4` | Preserved fields; `text1` is an alias of `text_content` |
| `side`, optional `highlight_right` | Preserved; right-side text fields can be inverted |
| Source `template_id` | Remapped through source IDs to newly created or identical existing templates |
| Nullable legacy template | Kept unassigned; product cannot print until a template is assigned |
| All eleven reference variable names | Same meanings; one render timestamp in configured timezone |
| QR size assumed 21 modules | Actual QR version and quiet zone determine magnification |
| `^PQ1` | One job with validated quantity and `^PQquantity,0,1,Y` |
| Raw text interpolation | Sanitized data and UTF-8 byte escaping with `^FH`; `^CI28` |
| Reference manual alphanumeric QR input | Manual `Bdddd` byte mode with UTF-8 byte count, correction M and mask 7 |
| Windows spooler / TSPL settings | Excluded. Admin creates explicit network ZPL printers |
| Kiosk users/passwords/PINs | Excluded. Local users provisioned with new Argon2 passwords |
| `print_log`, production orders and GPIO | Excluded. Independent append-only print-job audit |

Reprint retains original product/template snapshots, while time/operator are new.
The selected printer is taken from the current configured printer catalog, with
its own snapshot and DPI. Current product and original template must still exist
and be active. Changes to an existing product do not rewrite earlier audit data.

Imports never infer a network printer from a Windows printer name. Existing
products are skipped, never overwritten. Template name collisions with different
data block execution. Uploads are capped at 20 MiB and 10,000 records per table,
opened read-only, and removed after parsing. The dry-run stores the source digest,
validated catalog payload and target comparison for one hour. Execute rechecks
the target and commits the catalog and completed import marker atomically.

QR uses explicit byte input because Zebra automatic input excludes certain byte
values, including bytes found in UTF-8. The four-digit count is the number of
payload **bytes**, not Unicode characters. See the primary
[Zebra ^BQ command reference](https://docs.zebra.com/content/tcm/us/en/printers/software/zpl-pg/zpl-commands/%5Ebq.html).
Batch quantity follows the
[Zebra ^PQ command reference](https://docs.zebra.com/us/en/printers/software/zpl-pg/zpl-commands/%5Epq.html).
Text field hex escaping follows
[Zebra ^FH](https://docs.zebra.com/content/tcm/us/en/printers/software/zpl-pg/zpl-commands/%5Efh.html).
Text blocks use
[Zebra ^FB](https://docs.zebra.com/us/en/printers/software/zpl-pg/zpl-commands/%5Efb.html),
including explicit newline escapes and a conservative 3000-byte data limit.
