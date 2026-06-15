# Security Policy

## Reporting

Please report suspected vulnerabilities privately through GitHub Security Advisories.
Do not include exploit details in a public issue before maintainers have reviewed them.

## Data Handling

The deterministic analyzer reads source files from the selected local folder and writes its
cache under `.logicchart/`. It does not upload source code or require an API key.

The MCP server exposes only LogicChart model operations and an explicit project refresh.
Hosts should still require user approval before invoking tools that read or update local
project artifacts.
