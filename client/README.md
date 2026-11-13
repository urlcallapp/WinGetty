# WinGetty protocol handler (Windows client)

winget has no built-in URL protocol that a web page can use to trigger an
install from a specific source. These scripts add a safe `wingetty://`
handler so the Install buttons in the WinGetty catalog (`/catalog`) work
with one click.

## Files

| File | Purpose |
| --- | --- |
| `Register-WinGettyProtocol.ps1` | Registers the protocol for the current user and stores the allowed winget source name. |
| `Invoke-WinGettyProtocol.ps1` | The handler Windows calls when a `wingetty://` link is clicked. Validates and confirms, then runs winget. |
| `Unregister-WinGettyProtocol.ps1` | Removes the registration. |

## Setup (per machine)

```powershell
.\Register-WinGettyProtocol.ps1 -SourceName WinGetty
```

Use the same source name shown in the catalog's one-time setup command
(`winget source add -n <name> -t "Microsoft.Rest" -a https://<server>/wg/`).
Registration is per-user under `HKCU\Software\Classes` and needs no admin
rights. For fleet deployment, distribute the folder with GPO/Intune/SCCM
and run the register script in the user context.

## Security model

The handler is deliberately narrow:

- Only the `install` action exists. There is no way to pass a free-form
  command through the link.
- The package identifier and version must match strict allow-list patterns
  (`Publisher.App` style); shell metacharacters are rejected.
- The source name in the link must equal the source name configured at
  registration time, so a web page cannot redirect installs to an
  attacker-controlled winget source.
- winget receives a fixed argument array via `Start-Process -ArgumentList`;
  no link text is ever concatenated into a command line.
- The user confirms every install in a dialog before winget starts.

## Notes

- The scripts are unsigned. Sign them with your organization certificate
  for fleet rollout, or allow them with an ExecutionPolicy exception
  scoped to this folder.
- Requires winget (App Installer) on the machine and the WinGetty source
  added beforehand; the handler does not add sources itself.
