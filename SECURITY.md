# Security and privacy

Do not paste API keys, full screenshots with personal information, or runtime credential files into public GitHub issues. Reproduction reports should use public sample text and redact credentials and account identifiers.

Local OCR is the default. Translation sends recognized text to the selected service. Enabling cloud OCR sends the selected original image region to that OCR provider. Pinned-image annotations and mosaic do not alter the OCR input; change the original selection if a different recognition region is needed.

Saved API keys use Windows user encryption. Both installed and portable builds store configuration, credentials, logs, and application temporary files in `data` next to the EXE. There is no fallback to AppData when this directory is not writable. Uninstall retains configuration. Never include this directory in source exports or release assets. System registration and Windows shortcuts are optional and disabled by default. Windows itself may still maintain execution records; installer plugins may temporarily use the system temporary directory.

After creating the GitHub repository, enable private vulnerability reporting under repository security settings. Use that channel for security findings; until it is configured, contact the maintainer privately rather than creating a public issue with exploit details or secrets.

The supplied release is not Authenticode-signed. SHA-256 checksums identify exact files but do not establish publisher identity. Maintainers can sign the application and installer with their own certificate before release; regenerate checksums after signing. Do not disable Windows security tools to distribute or run a build.
