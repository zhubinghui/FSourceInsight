"""Suggest likely duplicate companies from their names alone; never merges anything."""
import re
import unicodedata
from collections import defaultdict

_LEGAL = {'sas', 'sasu', 'sarl', 'sa', 'inc', 'ltd', 'gmbh', 'france', 'group', 'groupe'}


def _keys(name):
    ascii_name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower()
    tokens = [token for token in re.findall(r'[a-z0-9]+', ascii_name) if token not in _LEGAL]
    if not tokens or len(''.join(tokens)) < 4:
        return []
    # Spacing variants share the first key, word-order variants the second.
    return [''.join(tokens), ' '.join(sorted(tokens))]


def duplicate_groups(companies):
    """Return lists of companies whose normalized names collide, keeper first."""
    parent = {company.id: company.id for company in companies}

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    first_with_key = {}
    for company in companies:
        for key in _keys(company.name):
            if key in first_with_key:
                parent[find(company.id)] = find(first_with_key[key])
            else:
                first_with_key[key] = company.id
    groups = defaultdict(list)
    for company in companies:
        groups[find(company.id)].append(company)
    result = [sorted(group, key=lambda c: (c.is_auto_created, c.id)) for group in groups.values() if len(group) > 1]
    return sorted(result, key=lambda group: group[0].name.lower())
