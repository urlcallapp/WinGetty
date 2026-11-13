# Added 2026-11-13 (urlcallapp/WinGetty fork): artifact-store intake.
"""Fetch a winget-download drop folder packaged as an archive from an
internal artifact store (Nexus, Artifactory, any static HTTP host).

Safety properties:

* download size is capped (header + streaming enforcement);
* only .zip, .tar.gz and .tgz payloads are accepted;
* archive members with absolute paths, drive letters, ``..`` components,
  symlinks, hardlinks or device entries are rejected;
* member count and total extracted size are capped;
* URLs are redacted (userinfo stripped) before they appear in any error
  or log message, so embedded credentials never leak into output.
"""

import base64
import os
import tarfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

DEFAULT_MAX_DOWNLOAD_BYTES = 4 * 1024**3  # 4 GiB
MAX_MEMBERS = 5000
MAX_EXTRACTED_BYTES = 4 * 1024**3


class ArtifactError(Exception):
    """Raised when an artifact cannot be fetched or safely extracted."""


def redact_url(url):
    """Return *url* with any userinfo (credentials) removed."""
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urllib.parse.urlunsplit((parts.scheme, host, parts.path, "", ""))


def fetch_artifact(url, dest_path, max_bytes=DEFAULT_MAX_DOWNLOAD_BYTES, timeout=120):
    """Download *url* to *dest_path*, enforcing a hard size cap.

    HTTP Basic credentials may be embedded in the URL
    (https://user:pass@host/file.zip); they are sent as an Authorization
    header and never appear in errors or logs.
    """
    safe_url = redact_url(url)
    parts = urllib.parse.urlsplit(url)
    headers = {"User-Agent": "wingetty-import"}
    if parts.username is not None:
        credentials = f"{urllib.parse.unquote(parts.username)}:{urllib.parse.unquote(parts.password or '')}"
        headers["Authorization"] = (
            "Basic " + base64.b64encode(credentials.encode()).decode()
        )
        # Remove userinfo from the request URL itself.
        url = safe_url
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            length = resp.headers.get("Content-Length")
            if length is not None and int(length) > max_bytes:
                raise ArtifactError(
                    f"artifact at {safe_url} is {int(length)} bytes, "
                    f"over the {max_bytes}-byte cap"
                )
            written = 0
            with open(dest_path, "wb") as out:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        raise ArtifactError(
                            f"artifact at {safe_url} exceeded the "
                            f"{max_bytes}-byte cap while downloading"
                        )
                    out.write(chunk)
            return written
    except urllib.error.URLError as e:
        raise ArtifactError(f"cannot fetch artifact {safe_url}: {e.reason}")


def _safe_member_name(name):
    """Normalize and validate one archive member name."""
    name = name.replace("\\", "/")
    if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
        raise ArtifactError(f"unsafe absolute path in archive: {name!r}")
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ArtifactError(f"path traversal in archive member: {name!r}")
    return "/".join(parts)


def safe_extract(archive_path, dest_dir):
    """Extract a .zip/.tar.gz archive into *dest_dir* with safety checks."""
    lower = archive_path.lower()
    if lower.endswith(".zip"):
        return _extract_zip(archive_path, dest_dir)
    if lower.endswith((".tar.gz", ".tgz")):
        return _extract_tar(archive_path, dest_dir)
    raise ArtifactError(
        f"unsupported artifact type for {os.path.basename(archive_path)} "
        "(expected .zip, .tar.gz or .tgz)"
    )


def _extract_zip(archive_path, dest_dir):
    count = 0
    total = 0
    with zipfile.ZipFile(archive_path) as zf:
        for info in zf.infolist():
            name = _safe_member_name(info.filename)
            if not name:
                continue
            # Unix symlink entries carry S_IFLNK in the external attributes.
            if (info.external_attr >> 16) & 0o120000 == 0o120000:
                raise ArtifactError(f"symlink in archive rejected: {name!r}")
            count += 1
            total += info.file_size
            if count > MAX_MEMBERS:
                raise ArtifactError(f"archive has more than {MAX_MEMBERS} members")
            if total > MAX_EXTRACTED_BYTES:
                raise ArtifactError("archive exceeds extracted-size cap")
            if info.is_dir():
                os.makedirs(os.path.join(dest_dir, name), exist_ok=True)
                continue
            target = os.path.join(dest_dir, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                remaining = info.file_size
                while remaining > 0:
                    chunk = src.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    out.write(chunk)
                    remaining -= len(chunk)
    return count


def _extract_tar(archive_path, dest_dir):
    count = 0
    total = 0
    with tarfile.open(archive_path, "r:gz") as tf:
        for member in tf:
            name = _safe_member_name(member.name)
            if not name:
                continue
            if member.issym() or member.islnk() or member.isdev():
                raise ArtifactError(
                    f"link/device member in archive rejected: {name!r}"
                )
            count += 1
            total += member.size
            if count > MAX_MEMBERS:
                raise ArtifactError(f"archive has more than {MAX_MEMBERS} members")
            if total > MAX_EXTRACTED_BYTES:
                raise ArtifactError("archive exceeds extracted-size cap")
            if member.isdir():
                os.makedirs(os.path.join(dest_dir, name), exist_ok=True)
                continue
            if not member.isfile():
                continue
            target = os.path.join(dest_dir, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            src = tf.extractfile(member)
            with open(target, "wb") as out:
                remaining = member.size
                while remaining > 0:
                    chunk = src.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    out.write(chunk)
                    remaining -= len(chunk)
    return count
