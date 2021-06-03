# Code reference extraction script

## config.json

You can use any JSON file to configure the scan. The config file identifies the repositories to scan along with any folders to exclude from the process.

The excluded folder names apply at any level of the scan, so if you exclude "media" then all folders named "media" are ignored.

## extract_coderefs.py

Main scanning script, which depends on the following environment variables:

- Required: set CODEREFS_REPO_ROOT to the path of the folders containing repositories listed in config.json.
- Optional: set CODEREFS_RESULTS_FOLDER to the output folder, otherwise "CodeRefResults" is used.

Run the script with `python extract_coderefs.py --config <path-to-json-config-file>`. If --config is omitted, it uses config.json in the current folder.