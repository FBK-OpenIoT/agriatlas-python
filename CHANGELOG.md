# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
- `agriatlas.login()`: authenticated `pystac_client.Client` with credentials from arguments,
  environment variables or a prompt, or an existing access token.
- Automatic access token refresh before every STAC request and download.
