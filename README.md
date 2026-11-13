<div id="top"></div>
<!--
*** Thanks for checking out the Best-README-Template. If you have a suggestion
*** that would make this better, please fork the repo and create a pull request
*** or simply open an issue with the tag "enhancement".
*** Don't forget to give the project a star!
*** Thanks again! Now go create something AMAZING! :D
-->



<!-- PROJECT SHIELDS -->
<!--
*** I'm using markdown "reference style" links for readability.
*** Reference links are enclosed in brackets [ ] instead of parentheses ( ).
*** See the bottom of this document for the declaration of the reference variables
*** for contributors-url, forks-url, etc. This is an optional, concise syntax you may use.
*** https://www.markdownguide.org/basic-syntax/#reference-style-links
-->




<!-- PROJECT LOGO -->
<br />
  <a href="https://github.com/thilojaeggi/WinGetty">
    <img src="https://raw.githubusercontent.com/thilojaeggi/WinGetty/main/src/wingetty.png" alt="Logo" height="128">
  </a>

<h1>WinGetty</h1>

WinGetty is a self-hosted winget package source. It's portable and can run on Linux, Windows, in Docker, locally and in any cloud.


## 🚀 Features

- Intuitive and easy to use Webinterface
- Add your own packages for internal or customized software with multiple versions, installers including architectures and scope
- **Automated import** of packages downloaded with `winget download` - point the importer at a folder or artifact store, no manual per-package UI work
- **End-user app catalog** at `/catalog` with search, copyable install commands and one-click install buttons
- **Safe `wingetty://` protocol handler** for Windows clients so catalog Install buttons trigger winget directly
- Search, list, show and install software - the core winget features all work
- Support for nested installers and installer switches
- Easy updating of package metadata
- Package download counter
- Support for multiple users and authentication
- Runs on Windows, Linux etc. using Docker

## 🚧 Not Yet Working or Complete
- Authentication (it's currently [not supported by winget](https://github.com/microsoft/winget-cli-restsource/issues/100))
- Probably other stuff? It's work-in-progress - please submit an issue and/or PR if you notice anything!

## 🧭 Getting Started

### 🐋 Docker
1. Install Docker on your machine. Refer to the [official Docker documentation](https://docs.docker.com/get-docker/) for instructions specific to your operating system.
2. Download the docker-compose.yml file from the main branch.
3. Open the docker-compose.yml file and modify the configuration values according to your preferences.  
The configurable options are:
* WINGETTY_SQLALCHEMY_DATABASE_URI: This parameter allows you to specify the database URI for storing WinGetty's data. By default, it is set to use SQLite with a file named database.db. You can use any database URI supported by SQLAlchemy, such as MySQL or PostgreSQL.
* WINGETTY_SECRET_KEY: This parameter sets the secret key used for securing WinGetty's sessions and other cryptographic operations. Replace the value with a random string.
* WINGETTY_ENABLE_REGISTRATION: By default, user registration is enabled (1). If you want to disable user registration, set this value to 0 after you have created your first user.
* WINGETTY_REPO_NAME: This parameter specifies the name of your WinGetty repository. You can change it to any desired name.
4. Start the WinGetty application using Docker Compose:
`docker-compose up -d`  
This command launches the WinGetty container in the background.
5. Access the web interface by opening your browser and navigating to http://localhost:8080.  
If you're running WinGetty on a remote server, replace localhost with the appropriate IP address or hostname.
6. Upon accessing the web interface for the first time, you will be prompted to register a user, this user will become the admin user by default.

> ⚠️ **Note**: WinGet requires HTTPS for secure communication and without it WinGet will throw an error. It is recommended to put WinGetty behind a reverse proxy with a client-trusted SSL/TLS certificate.  
By using a reverse proxy with HTTPS, you can ensure secure transmission of data between clients and WinGetty. Popular reverse proxy solutions include NGINX, Apache, and Caddy. Please refer to the documentation of your chosen reverse proxy for detailed instructions on configuring SSL/TLS certificates.

### ⬆️ Upgrading an existing deployment
WinGetty manages its schema with database migrations, and the container applies them automatically on start (`start.sh` runs `flask db upgrade`). To upgrade safely:

1. Back up the database first. For the default SQLite setup, copy the database file (and the `packages/` directory) while the container is stopped; for MySQL/PostgreSQL, take a dump with your usual tooling.
2. Pull the new image and start the container. The migration runs automatically and only applies the changes since your current version - existing packages, versions, installers, users and settings are preserved.
3. If the container fails to start after an upgrade, restore the backup and report the migration error as an issue.

> ⚠️ **Note**: The migration chain expects a database that was created and maintained through `flask db upgrade` (as the container does). If you ever created the schema through the application models directly (`db.create_all()`) without running the migrations, the upgrade chain cannot apply to it - export and re-import your packages instead, or ask for help in an issue before upgrading.

### 🪄 Using WinGetty

You can test the WinGet API by opening `http://localhost:8080/wg/information` in a browser or with `curl` / `Invoke-RestMethod`.

Now you can add it as a package source in winget using the command provided in the 'Setup' tab in the webinterface:

```
winget source add -n WinGetty -t "Microsoft.Rest" -a https://wingetty.dev/wg/
```

and query it:

```
❯ winget search Signal -s WinGetty
Name   ID            Version
----------------------------
Signal Signal.Signal 1.0.0
```
and install packages:
```
❯ winget install Signal.Signal -s WinGetty
Found bottom [Signal.Signal] Version 1.0.0
This application is licensed to you by its owner.
Microsoft is not responsible for, nor does it grant any licenses to, third-party packages.
Downloading  https://wingetty.dev/api/download/Signal.Signal/1.0.0/x64/both
  ██████████████████████████████  112 MB /  112 MB
Successfully verified installer hash
Starting package install...
Successfully installed

~ took 12s
❯
```

### 📥 Automated package import

On an internet-connected machine, download packages with winget. Each
download produces the installer plus a generated YAML manifest:

```
winget download --id 7zip.7zip -d .\drops\7zip
```

Carry the drop folders (or sync your artifact store into one) to the
WinGetty side and run the importer - it parses the YAML, verifies the
SHA256 of every installer against the manifest, and registers everything
in WinGetty. Re-running it is safe: installers that already exist are
skipped, and every run writes a JSON report of what was added, skipped or
failed.

On the WinGetty host (same `WINGETTY_*` environment as the app):

```
python -m wingetty_import /srv/winget-drops --local
```

From any machine, through the REST API:

```
python -m wingetty_import /srv/winget-drops \
    --server https://wingetty.internal --username svc-import
```

Continuous intake (for an artifact store synced into the drop folder):

```
python -m wingetty_import /srv/winget-drops --local --watch 600
```

Pull a packaged drop folder straight from an internal artifact store
(Nexus, Artifactory, any static HTTP host). Archives (.zip/.tar.gz) are
downloaded with a size cap (`--max-artifact-bytes`) and extracted with
path-traversal and link protection; URLs are redacted in log output so
embedded credentials never leak:

```
python -m wingetty_import --artifact-url https://nexus.internal/drops/latest.zip \
    --server https://wingetty.internal --username svc-import
```

Installer switches (`Silent`, `Custom`, ...) and manifest `Dependencies`
(package and external) are carried through into WinGetty and served back
to winget clients in the generated manifests.

Notes and limits:
- Stick to regular exe/msi/zip packages. Microsoft Store (msstore) source
  apps need Entra ID to download and carry offline license files, and
  manifests with `DownloadCommandProhibited` cannot be downloaded at all.
- The manifest's original vendor URL is only used to locate the downloaded
  file; WinGetty always serves installers from its own internal URL, so no
  internet URL leaks into the generated manifests.
- A small "bootstrapper" installer that downloads the rest of itself from
  the internet at install time will not work in a disconnected network.
  Make sure the installers you import are complete and their dependencies
  are available internally.

### 🛍️ End-user catalog

WinGetty serves a user-facing catalog at `/catalog` (no login required by
default; toggle it in Settings). Users see the available apps, copy the
ready-made `winget install` command or click Install. The one-time source
setup command is shown at the top of the page.

Clicking an app card opens its details view: the long description, author,
license, homepage and other links, tags, release notes and installation
notes. This metadata comes from the app's winget YAML manifest
(defaultLocale and version fields such as `Description`, `Author`,
`License`, `PackageUrl`, `Tags`, `ReleaseNotes`); the importer and the
REST API store it on the version when the YAML provides it. Re-importing
a package with richer YAML fills in details on versions that are missing
them (existing values are never overwritten), so catalogs created before
this feature gain details on the next import. Manifest metadata is
sanitized on intake - unknown fields are dropped and only `http(s)` URLs
survive - and the details view shows whatever the manifest actually
provided, nothing invented.

Settings: `Enable user catalog`, `Catalog requires login`,
`Catalog source name`, `Catalog install links`.

### 🖱️ One-click installs from the browser (wingetty://)

winget has no built-in URL protocol, so the catalog's Install buttons use a
small Windows component from `client/`: it registers a `wingetty://` handler
that validates the package identifier, only allows the install action, pins
the allowed source name and asks the user for confirmation before running
winget with a fixed argument list - links can never inject commands or swap
the source. See `client/README.md`.

### 🧪 Development

```
pip install -r requirements.txt -r requirements-dev.txt
pytest -q                 # backend, importer, winget API and catalog tests
npm ci && npm run build:css   # rebuild the Tailwind CSS
```

Tests also run in GitHub Actions on every push and pull request.

### 📜 License and source availability

WinGetty is licensed under the [AGPL-3.0](LICENSE.md); original work
© Thilo Jaeggi, with modifications dated 2026-11-13 listed in
[NOTICE.md](NOTICE.md). Because users interact with WinGetty over a
network, every running instance offers its corresponding source at
`/source` (linked from the footer of every page, no login required).
The page also serves a source archive from the server itself at
`/source/archive`, which keeps the offer working on air-gapped networks
where users cannot reach GitHub. The Dockerfile builds this archive
automatically at image build time; on a manual deployment run
`scripts/build-source-archive.sh` after each update. The archive contains
a `SOURCE_VERSION` file with the exact revision it was built from.

<hr>
    <a href="https://github.com/thilojaeggi/WinGetty/issues">Report Issue</a>
    ·
    <a href="https://github.com/thilojaeggi/WinGetty/issues">Request Feature</a>

<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->
[contributors-shield]: https://img.shields.io/github/contributors/thilojaeggi/wingetty.svg?style=flat-square
[contributors-url]: https://github.com/thilojaeggi/WinGetty/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/thilojaeggi/WinGetty.svg?style=flat-square
[forks-url]: https://github.com/thilojaeggi/WinGetty/network/members
[stars-shield]: https://img.shields.io/github/stars/thilojaeggi/WinGetty.svg?style=flat-square
[stars-url]: https://github.com/thilojaeggi/WinGetty/stargazers
[issues-shield]: https://img.shields.io/github/issues/thilojaeggi/WinGetty.svg?style=flat-square
[issues-url]: https://github.com/thilojaeggi/WinGetty/issues
[license-shield]: https://img.shields.io/github/license/thilojaeggi/WinGetty.svg?style=flat-square
[license-url]: https://github.com/thilojaeggi/WinGetty/blob/master/LICENSE.txt
[linkedin-shield]: https://img.shields.io/badge/-LinkedIn-black.svg?style=flat-square&logo=linkedin&colorB=555
[linkedin-url]: https://linkedin.com/in/linkedin_username
[product-screenshot]: images/screenshot.png
[Next.js]: https://img.shields.io/badge/next.js-000000?style=for-the-badge&logo=nextdotjs&logoColor=white
[Next-url]: https://nextjs.org/
[React.js]: https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB
[React-url]: https://reactjs.org/
[Vue.js]: https://img.shields.io/badge/Vue.js-35495E?style=for-the-badge&logo=vuedotjs&logoColor=4FC08D
[Vue-url]: https://vuejs.org/
[Angular.io]: https://img.shields.io/badge/Angular-DD0031?style=for-the-badge&logo=angular&logoColor=white
[Angular-url]: https://angular.io/
[Svelte.dev]: https://img.shields.io/badge/Svelte-4A4A55?style=for-the-badge&logo=svelte&logoColor=FF3E00
[Svelte-url]: https://svelte.dev/
[Laravel.com]: https://img.shields.io/badge/Laravel-FF2D20?style=for-the-badge&logo=laravel&logoColor=white
[Laravel-url]: https://laravel.com
[Bootstrap.com]: https://img.shields.io/badge/Bootstrap-563D7C?style=for-the-badge&logo=bootstrap&logoColor=white
[Bootstrap-url]: https://getbootstrap.com
[JQuery.com]: https://img.shields.io/badge/jQuery-0769AD?style=for-the-badge&logo=jquery&logoColor=white
[JQuery-url]: https://jquery.com
[Flutter]: https://img.shields.io/badge/Flutter-%2302569B.svg?style=for-the-badge&logo=Flutter&logoColor=white
[Flutter-url]: https://flutter.dev
[Dart]: https://img.shields.io/badge/dart-%230175C2.svg?style=for-the-badge&logo=dart&logoColor=white
[Dart-url]: https://dart.dev
[Swift]: https://img.shields.io/badge/swift-F54A2A?style=for-the-badge&logo=swift&logoColor=white
[Swift-url]: https://www.swift.org/
