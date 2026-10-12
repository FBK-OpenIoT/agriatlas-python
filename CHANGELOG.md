# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
- `agriatlas.login()`: authenticated `pystac_client.Client` with credentials from arguments,
  environment variables or a prompt. A custom `AgriAtlasConfig` can be passed as `client_config`.
- `agriatlas.logout()`, `agriatlas.get_session()` and `agriatlas.current_session()` to manage the
  default session.
- `agriatlas.download(item, target_path, roles=("data",))`: download the assets of an Item with the
  given roles (all of them with `roles=None`) and return `{asset_key: Path}`.
- `agriatlas.download_asset(asset, target)`: download a single asset, with a progress bar. Downloads
  are verified against the asset's `file:checksum` when available. Files already present with the
  expected checksum (or size, if there is no checksum) are skipped. Missing directories are created.
- HTTP 401, 403 and 404 on download raise `NotLoggedInError`, `AuthenticationError` and
  `AgriAtlasError`.
- Automatic access token refresh before every STAC request and download.
