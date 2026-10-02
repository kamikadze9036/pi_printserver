`legacy-copy.db` is a synthetic, self-contained SQLite fixture with one template
and one product. It contains no kiosk data or credentials. Generate it from the
repository root with:

```sh
python backend/tests/make_legacy_fixture.py frontend/e2e/fixtures/legacy-copy.db
```
