"""Tests for strict-env. Every case loads from an explicit mapping, never the
real process environment, so the suite is deterministic and offline."""

import pytest

from strict_env import load, field, Config, EnvError


def test_happy_path_types():
    cfg = load(
        {
            "PORT": field(int, default=8000),
            "DEBUG": field(bool, default=False),
            "DATABASE_URL": field(str),
            "TIMEOUT": field(float, default=5.0),
            "HOSTS": field(list, default=[]),
        },
        {"PORT": "9000", "DEBUG": "true", "DATABASE_URL": "postgres://x", "HOSTS": "a.com, b.com"},
    )
    assert cfg.PORT == 9000
    assert cfg.DEBUG is True
    assert cfg.DATABASE_URL == "postgres://x"
    assert cfg.TIMEOUT == 5.0  # default kicked in
    assert cfg.HOSTS == ["a.com", "b.com"]


def test_defaults_used_when_unset():
    cfg = load({"PORT": field(int, default=8000)}, {})
    assert cfg.PORT == 8000


def test_required_missing_collects_all_errors():
    with pytest.raises(EnvError) as exc:
        load({"A": field(str), "B": field(int), "C": field(str)}, {"C": "ok"})
    assert len(exc.value.errors) == 2
    joined = "\n".join(exc.value.errors)
    assert "A is required" in joined
    assert "B is required" in joined
    assert "C" not in joined


def test_invalid_int_reported_with_value():
    with pytest.raises(EnvError) as exc:
        load({"PORT": field(int)}, {"PORT": "not-a-number"})
    assert "PORT is invalid" in exc.value.errors[0]
    assert "not-a-number" in exc.value.errors[0]


def test_int_is_strict_about_floats():
    with pytest.raises(EnvError):
        load({"N": field(int)}, {"N": "3.5"})


@pytest.mark.parametrize("raw,expected", [
    ("1", True), ("true", True), ("YES", True), ("on", True),
    ("0", False), ("false", False), ("No", False), ("off", False),
])
def test_bool_parsing(raw, expected):
    cfg = load({"F": field(bool)}, {"F": raw})
    assert cfg.F is expected


def test_bool_rejects_garbage():
    with pytest.raises(EnvError) as exc:
        load({"F": field(bool)}, {"F": "ture"})
    assert "boolean" in exc.value.errors[0]


def test_list_of_ints():
    cfg = load({"IDS": field(list, item_type=int)}, {"IDS": "1, 2, 3"})
    assert cfg.IDS == [1, 2, 3]


def test_list_drops_empty_items():
    cfg = load({"XS": field(list)}, {"XS": "a,, b, ,c"})
    assert cfg.XS == ["a", "b", "c"]


def test_choices_enforced():
    with pytest.raises(EnvError) as exc:
        load({"ENV": field(str, choices=["dev", "prod"])}, {"ENV": "staging"})
    assert "must be one of" in exc.value.errors[0]


def test_choices_pass():
    cfg = load({"ENV": field(str, choices=["dev", "prod"])}, {"ENV": "prod"})
    assert cfg.ENV == "prod"


def test_custom_validator_predicate():
    with pytest.raises(EnvError):
        load({"PORT": field(int, validate=lambda v: 1 <= v <= 65535)}, {"PORT": "70000"})


def test_custom_validator_raising_is_a_rejection():
    def must_start_https(v):
        if not v.startswith("https://"):
            raise ValueError("must use https")
        return True
    with pytest.raises(EnvError) as exc:
        load({"URL": field(str, validate=must_start_https)}, {"URL": "http://x"})
    assert "must use https" in exc.value.errors[0]


def test_custom_parser_callable():
    def csv_pairs(raw):
        return dict(p.split("=") for p in raw.split(","))
    cfg = load({"MAP": field(csv_pairs)}, {"MAP": "a=1,b=2"})
    assert cfg.MAP == {"a": "1", "b": "2"}


def test_custom_parser_value_error_is_reported():
    def only_even(raw):
        n = int(raw)
        if n % 2:
            raise ValueError("must be even")
        return n
    with pytest.raises(EnvError) as exc:
        load({"N": field(only_even)}, {"N": "3"})
    assert "must be even" in exc.value.errors[0]


def test_secret_value_is_masked_in_errors():
    with pytest.raises(EnvError) as exc:
        load({"API_KEY": field(int, secret=True)}, {"API_KEY": "sk-supersecret"})
    assert "sk-supersecret" not in exc.value.errors[0]
    assert "API_KEY is invalid" in exc.value.errors[0]


def test_optional_without_default_is_none():
    cfg = load({"MAYBE": field(str, required=False)}, {})
    assert cfg.MAYBE is None


def test_config_item_and_attr_and_dict():
    cfg = load({"A": field(str)}, {"A": "x"})
    assert cfg["A"] == "x"
    assert cfg.A == "x"
    assert cfg.as_dict() == {"A": "x"}
    assert "A" in cfg


def test_config_is_read_only():
    cfg = load({"A": field(str)}, {"A": "x"})
    with pytest.raises(AttributeError):
        cfg.A = "y"


def test_missing_attribute_raises_attributeerror():
    cfg = load({"A": field(str)}, {"A": "x"})
    with pytest.raises(AttributeError):
        _ = cfg.NOPE


def test_bad_schema_entry_is_valueerror_not_enverror():
    with pytest.raises(ValueError):
        load({"A": "not-a-dict"}, {"A": "x"})


def test_plain_dict_spec_without_field_helper():
    cfg = load({"PORT": {"type": int, "default": 3000}}, {"PORT": "80"})
    assert cfg.PORT == 80


def test_explicit_required_overrides_default_presence():
    # default present but required forced True -> still required
    with pytest.raises(EnvError):
        load({"A": {"type": str, "default": "x", "required": True}}, {})
