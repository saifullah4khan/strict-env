# strict-env

Declare the environment your app needs, then load it all at once and fail loudly if anything is wrong.

## The problem

Most services read configuration straight out of `os.environ` scattered across the codebase. A missing `DATABASE_URL` or a `DEBUG=ture` typo then surfaces hours later as an `AttributeError` deep in a request handler, or worse, as a service that boots "fine" with the wrong settings. And because the checks are spread out, you fix one bad variable, redeploy, and immediately trip over the next one.

`strict-env` moves all of that to startup. You write one schema, call `load()` once, and get back a settled config object. If two variables are missing and a third is malformed, you get a single error listing all three, so one restart tells you everything that is wrong.

## Quickstart

```bash
pip install strict-env   # or drop the single module into your project
```

```python
from strict_env import load, field

cfg = load({
    "DATABASE_URL": field(str),                      # required
    "PORT":         field(int, default=8000),
    "DEBUG":        field(bool, default=False),
    "ALLOWED_HOSTS": field(list, default=[]),
    "LOG_LEVEL":    field(str, choices=["debug", "info", "warning"], default="info"),
    "API_KEY":      field(str, secret=True),         # kept out of error output
})

app.run(host="0.0.0.0", port=cfg.PORT, debug=cfg.DEBUG)
```

If `DATABASE_URL` and `API_KEY` are unset and `PORT` is `"abc"`, `load()` raises once:

```
strict_env.EnvError: Invalid environment configuration:
  - DATABASE_URL is required but not set
  - PORT is invalid: invalid literal for int() with base 10: 'abc' (got 'abc')
  - API_KEY is required but not set
```

Values are read by attribute (`cfg.PORT`) or item (`cfg["PORT"]`), and the object is read-only so nothing downstream can quietly mutate your config.

## Design decisions

**Collect every error, then raise once.** The whole point is to make a bad deployment cheap to diagnose. Raising on the first missing variable would turn a one-line fix into a fix-restart-repeat loop, so `load()` walks the entire schema, accumulates problems, and raises a single `EnvError` whose `.errors` list holds each message.

**Strict coercion, not clever coercion.** `int` rejects `"3.5"` and `bool` rejects `"ture"` instead of guessing. Booleans accept an explicit set (`1/0`, `true/false`, `yes/no`, `on/off`); anything outside it is treated as a mistake, because silently reading a typo as `False` is exactly the kind of bug this library exists to prevent.

**Secrets never appear in error text.** Mark a field `secret=True` and neither the raw value nor a parser message that might quote it (the standard `int()` error embeds the offending string) makes it into the `EnvError`. Startup errors end up in logs and CI output, and that is the last place a token should leak.

**The environment is injectable.** `load(schema, environ=...)` takes any mapping, defaulting to `os.environ`. Passing a plain dict is what makes configuration testable without monkeypatching global state, and every test in this repo uses it.

**Required unless a default is given.** A field with a `default` is optional; one without is required. You can override either way with `required=`, but the common case needs no ceremony.

**No dependencies.** It is a single standard-library module. Configuration loading should not drag a dependency tree into your image.

## Configuration reference

Each schema entry is a spec dict, most easily built with `field()`:

| Option | Meaning | Default |
| --- | --- | --- |
| `type` | `str`, `int`, `float`, `bool`, `list`, or any `str -> value` callable | `str` |
| `default` | value used when the variable is unset; supplying it makes the field optional | (none, so required) |
| `required` | force required or optional explicitly | required unless `default` given |
| `secret` | keep the value out of all error messages | `False` |
| `choices` | restrict the parsed value to a fixed set | none |
| `validate` | predicate run after parsing; return `False` (or raise `ValueError`) to reject | none |
| `item_type` | element type when `type` is `list` | `str` |

A custom parser is just a callable that turns the raw string into a value and raises `ValueError` on bad input:

```python
from urllib.parse import urlparse

def url(raw):
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("not a valid URL")
    return parsed

cfg = load({"WEBHOOK_URL": field(url)}, {"WEBHOOK_URL": "https://example.com/hook"})
```

## Testing

```bash
pip install pytest
pytest
```

The suite is fully offline: every case passes an explicit mapping to `load()`, so there is no reliance on the real process environment.

## License

MIT. See [LICENSE](LICENSE).
