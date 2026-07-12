"""strict-env: fail-fast, typed environment configuration for Python.

Declare the environment variables your app needs, with types and defaults, and
load them all at once. Every missing or malformed variable is collected and
reported in a single error at startup, so a misconfigured deployment tells you
everything that is wrong in one shot instead of blowing up one variable at a
time in production.

Public API:
    load(schema, environ=None) -> Config
    Config          (attribute + item access to the loaded values)
    EnvError        (raised once, listing every problem)
    field(...)      (small helper for building a schema entry)
"""

from __future__ import annotations

import os
from typing import Any, Callable, Iterable, Mapping, Optional

__all__ = ["load", "Config", "EnvError", "field"]
__version__ = "0.1.0"

_MISSING = object()

# Strings we accept as booleans. Anything else is a configuration error rather
# than being silently coerced, because a typo like DEBUG=ture should fail loudly.
_TRUE = {"1", "true", "yes", "y", "on"}
_FALSE = {"0", "false", "no", "n", "off"}


class EnvError(Exception):
    """Raised once when one or more variables are missing or invalid.

    The individual problems are available on ``.errors`` as a list of strings,
    which is handy if you want to render them somewhere other than a traceback.
    """

    def __init__(self, errors: Iterable[str]):
        self.errors = list(errors)
        body = "\n".join("  - " + e for e in self.errors)
        super().__init__("Invalid environment configuration:\n" + body)


class Config:
    """The result of a successful :func:`load`.

    Values are reachable by attribute (``cfg.PORT``) or by item
    (``cfg[\"PORT\"]``). It is intentionally read-only; treat it as settled
    configuration, not a mutable bag.
    """

    def __init__(self, values: Mapping[str, Any]):
        object.__setattr__(self, "_values", dict(values))

    def __getattr__(self, name: str) -> Any:
        try:
            return self._values[name]
        except KeyError:
            raise AttributeError(name) from None

    def __getitem__(self, name: str) -> Any:
        return self._values[name]

    def __contains__(self, name: str) -> bool:
        return name in self._values

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("Config is read-only")

    def as_dict(self) -> dict:
        """Return a plain dict copy of the loaded values."""
        return dict(self._values)

    def __repr__(self) -> str:
        return "Config(" + ", ".join(sorted(self._values)) + ")"


def field(
    type: Any = str,
    *,
    default: Any = _MISSING,
    required: Optional[bool] = None,
    secret: bool = False,
    choices: Optional[Iterable[Any]] = None,
    validate: Optional[Callable[[Any], bool]] = None,
    item_type: Any = str,
) -> dict:
    """Build a schema entry.

    You can write the dict by hand; this helper just gives editors something to
    autocomplete and keeps call sites readable.

    ``type``      one of ``str``, ``int``, ``float``, ``bool``, ``list``, or any
                  callable that takes the raw string and returns the parsed value
                  (raise ``ValueError`` inside it to signal an invalid value).
    ``default``   supplying it makes the variable optional.
    ``required``  force required/optional explicitly; defaults to \"required
                  unless a default was given\".
    ``secret``    keep the value out of error messages (for tokens, passwords).
    ``choices``   restrict the parsed value to a fixed set.
    ``validate``  extra predicate run after parsing; return False to reject.
    ``item_type`` element type when ``type`` is ``list``.
    """
    spec: dict = {"type": type, "secret": secret, "item_type": item_type}
    if default is not _MISSING:
        spec["default"] = default
    if required is not None:
        spec["required"] = required
    if choices is not None:
        spec["choices"] = choices
    if validate is not None:
        spec["validate"] = validate
    return spec


def _coerce_scalar(kind: str, raw: str) -> Any:
    if kind == "str":
        return raw
    if kind == "int":
        # int("3.0") raises ValueError, which is what we want: be strict.
        return int(raw)
    if kind == "float":
        return float(raw)
    if kind == "bool":
        low = raw.strip().lower()
        if low in _TRUE:
            return True
        if low in _FALSE:
            return False
        raise ValueError("expected a boolean (e.g. true/false, 1/0, yes/no)")
    raise ValueError("unknown type " + kind)  # pragma: no cover


def _name_of(kind: Any) -> str:
    return {str: "str", int: "int", float: "float", bool: "bool"}.get(kind, "str")


def _parse(spec: dict, raw: str) -> Any:
    kind = spec["type"]

    if callable(kind) and kind not in (str, int, float, bool, list):
        # A user-supplied parser. Let it raise ValueError for bad input.
        return kind(raw)

    if kind is list:
        item_type = spec.get("item_type", str)
        parts = [p.strip() for p in raw.split(",")]
        parts = [p for p in parts if p]
        if item_type is str:
            return parts
        return [_coerce_scalar(_name_of(item_type), p) for p in parts]

    return _coerce_scalar(_name_of(kind), raw)


def load(schema: Mapping[str, dict], environ: Optional[Mapping[str, str]] = None) -> Config:
    """Load and validate configuration against ``schema``.

    ``schema`` maps a variable name to a spec dict (see :func:`field`). Pass a
    mapping as ``environ`` to load from something other than ``os.environ`` --
    this is what makes the whole thing trivially testable.

    Returns a :class:`Config` on success. Raises :class:`EnvError` listing every
    problem if anything is missing or malformed. Raises :class:`ValueError` for a
    malformed schema, since that is a programming error, not a config error.
    """
    src = os.environ if environ is None else environ
    values: dict = {}
    errors: list = []

    for name, spec in schema.items():
        if not isinstance(spec, dict):
            raise ValueError("schema entry for " + repr(name) + " must be a dict")

        has_default = "default" in spec
        required = spec.get("required", not has_default)
        secret = spec.get("secret", False)

        raw = src.get(name, _MISSING)

        if raw is _MISSING:
            if required:
                errors.append(name + " is required but not set")
            elif has_default:
                values[name] = spec["default"]
            else:
                values[name] = None
            continue

        try:
            parsed = _parse(spec, raw)
        except ValueError as exc:
            if secret:
                # Never echo the raw value or a parser message that might quote
                # it (int() and friends include the offending string).
                errors.append(name + " is invalid")
            else:
                errors.append(name + " is invalid: " + str(exc) + " (got " + repr(raw) + ")")
            continue

        choices = spec.get("choices")
        if choices is not None and parsed not in choices:
            allowed = ", ".join(map(repr, choices))
            shown = "" if secret else " " + repr(parsed)
            errors.append(name + " must be one of [" + allowed + "], got" + shown)
            continue

        validate = spec.get("validate")
        if validate is not None:
            reason = "failed validation"
            try:
                ok = validate(parsed)
            except Exception as exc:  # a raising validator is still a rejection
                ok = False
                reason = str(exc) or exc.__class__.__name__
            if not ok:
                shown = "" if secret else " (got " + repr(raw) + ")"
                errors.append(name + " " + reason + shown)
                continue

        values[name] = parsed

    if errors:
        raise EnvError(errors)

    return Config(values)
