"""Runnable example. Try it with good and bad environments:

    PORT=9000 DATABASE_URL=postgres://localhost/app API_KEY=sk-123 python example.py
    PORT=abc python example.py     # see every problem reported at once
"""

from strict_env import load, field, EnvError


SCHEMA = {
    "DATABASE_URL": field(str),
    "PORT": field(int, default=8000, validate=lambda p: 1 <= p <= 65535),
    "DEBUG": field(bool, default=False),
    "ALLOWED_HOSTS": field(list, default=[]),
    "LOG_LEVEL": field(str, choices=["debug", "info", "warning"], default="info"),
    "API_KEY": field(str, secret=True),
}


def main() -> int:
    try:
        cfg = load(SCHEMA)
    except EnvError as exc:
        print(exc)
        return 1

    print("Loaded configuration:")
    for key, value in sorted(cfg.as_dict().items()):
        shown = "***" if key == "API_KEY" else value
        print(f"  {key} = {shown!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
