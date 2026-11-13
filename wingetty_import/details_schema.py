# Added 2026-11-13 (urlcallapp/WinGetty fork): catalog package details validation.
"""Sanitizing of the optional per-version "details" metadata.

The details object carries the extra metadata a winget YAML manifest
provides beyond what WinGetty stores in dedicated columns (homepage,
license, tags, long description, release notes, ...). It is persisted on
``PackageVersion.details`` and shown in the end-user catalog when a card
is clicked.

Manifest content is untrusted input, so everything that enters the
database passes through :func:`sanitize_version_details`:

- unknown keys are dropped (allowlist below);
- scalar values are coerced to stripped, length-capped strings;
- URL fields only survive with an ``http://`` or ``https://`` scheme, so
  ``javascript:`` or ``file:`` values can never become links in the UI;
- lists (tags, documentations) are normalized and capped.

The same function is applied again when the catalog API serializes
details, so records edited through other paths are constrained too.
"""

# Scalar text fields (winget YAML key -> details key, max length).
_TEXT_FIELDS = {
    "Description": ("description", 8000),
    "Author": ("author", 200),
    "License": ("license", 200),
    "Copyright": ("copyright", 500),
    "Moniker": ("moniker", 100),
    "ReleaseDate": ("release_date", 40),
    "ReleaseNotes": ("release_notes", 8000),
    "InstallationNotes": ("installation_notes", 4000),
}

# URL fields; only http(s) values are kept.
_URL_FIELDS = {
    "PackageUrl": "homepage",
    "PublisherUrl": "publisher_url",
    "PublisherSupportUrl": "publisher_support_url",
    "PrivacyUrl": "privacy_url",
    "LicenseUrl": "license_url",
    "CopyrightUrl": "copyright_url",
    "ReleaseNotesUrl": "release_notes_url",
    "PurchaseUrl": "purchase_url",
}

_MAX_URL_LENGTH = 500
_MAX_TAGS = 16
_MAX_TAG_LENGTH = 64
_MAX_DOCS = 8
_MAX_DOC_LABEL_LENGTH = 128


def _clean_text(value, max_length):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_length]


def _clean_url(value):
    text = _clean_text(value, _MAX_URL_LENGTH)
    if text is None:
        return None
    if not text.lower().startswith(("http://", "https://")):
        return None
    return text


def sanitize_version_details(data):
    """Return a sanitized details dict, dropping anything not allowlisted.

    Accepts either raw winget YAML keys (``Description``, ``PackageUrl``,
    ``Tags`` ...) or already-normalized details keys (``description``,
    ``homepage`` ...); both map onto the same output. Returns an empty
    dict when nothing usable remains.
    """
    if not isinstance(data, dict):
        return {}

    details = {}

    for yaml_key, (out_key, max_length) in _TEXT_FIELDS.items():
        value = data.get(yaml_key, data.get(out_key))
        text = _clean_text(value, max_length)
        if text is not None:
            details[out_key] = text

    for yaml_key, out_key in _URL_FIELDS.items():
        value = data.get(yaml_key, data.get(out_key))
        url = _clean_url(value)
        if url is not None:
            details[out_key] = url

    tags = data.get("Tags", data.get("tags"))
    if isinstance(tags, str):
        tags = [tags]
    if isinstance(tags, list):
        clean_tags = []
        for tag in tags:
            text = _clean_text(tag, _MAX_TAG_LENGTH)
            if text is not None:
                clean_tags.append(text)
            if len(clean_tags) >= _MAX_TAGS:
                break
        if clean_tags:
            details["tags"] = clean_tags

    documentations = data.get("Documentations", data.get("documentations"))
    if isinstance(documentations, list):
        clean_docs = []
        for doc in documentations:
            if not isinstance(doc, dict):
                continue
            label = _clean_text(
                doc.get("DocumentLabel", doc.get("label")), _MAX_DOC_LABEL_LENGTH
            )
            url = _clean_url(doc.get("DocumentUrl", doc.get("url")))
            entry = {}
            if label is not None:
                entry["label"] = label
            if url is not None:
                entry["url"] = url
            if entry:
                clean_docs.append(entry)
            if len(clean_docs) >= _MAX_DOCS:
                break
        if clean_docs:
            details["documentations"] = clean_docs

    return details
