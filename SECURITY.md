# Security Policy

## Supported Versions

This project is currently pre-1.0. Security fixes are applied to the `main`
branch.

## Reporting a Vulnerability

Do not open a public issue for vulnerabilities, secrets, or examples containing
real account/routing information. Use GitHub's private vulnerability reporting
if available on this repository, or contact the maintainer privately.

## Sensitive Local Data

Generated PDFs, `config.local.yaml`, local SQLite registers, downloaded fonts,
and local routing-directory files may contain sensitive financial information.
These files are ignored by Git and should not be committed.
