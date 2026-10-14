"""YAML in and out, shared by v2 and v3 for phase and epic manifests.

Dates stay strings (no implicit timestamp conversion), so values round-trip unchanged and stay
JSON-serialisable.
"""
import yaml


class _Loader(yaml.SafeLoader):
    pass


_Loader.yaml_implicit_resolvers = {
    key: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load(text: str):
    return yaml.load(text, Loader=_Loader)


def dump(data) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100)
