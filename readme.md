# Code reference extraction script

## config.json

Config.json identifies the repositories to scan along with folder you want to exclude. An individual repository can be disabled in the config file.

Because the scanning script relies on information in the .openpublishing.config.json and docfx.json files, the opc_folder and docfx_folder specify where these files are located. If they're located in the repository root, set these to ""; otherwise set them to the appropriate subfolder(s).

The excluded folder names apply at any level of the scan, so if you exclude "media" then the script ignores all folders named "media".

## extract_coderefs.py

Main scanning script. Set environment variables first, then run `python extract_coderefs.py [--config <path-to-json-config-file>]`. If --config is omitted, the script uses config.json in the current folder.

The script's output is formatted as CSV so you can direct output to a file and sort/filter in Excel.

The utilities.py file just contains support functions for the main script.

### Environment variables

- Required: set CODEREFS_REPO_ROOT to the path of the folders containing repositories listed in config.json.
- Optional: set CODEREFS_RESULTS_FOLDER to the output folder, otherwise "data" is used.
- Required: GITHUB_USER: the GitHub user with which to authenticate API calls.
- Required: GITHUB_ACCESS_TOKEN: one of the user's GitHub personal access tokens from https://github.com/settings/tokens

It's helpful to create a setenv.cmd script to set these whenever you open a new shell.

The GitHub username and access token are required for GitHub API call to avoid being throttled to 60 calls per hour. Running the script in a larger repository (such as the Azure documentation) that contains hundreds or thousands of code references will easily exceed the limit. (The authorized limit is 5000 calls per hour, so an even more complex repository might yet exceed rate limits and would need to be handled differently.)

You also need to [authorize the token to access the necessary organizations](https://docs.github.com/en/github/authenticating-to-github/authenticating-with-saml-single-sign-on/authorizing-a-personal-access-token-for-use-with-saml-single-sign-on). For the Azure docs repo, applicable samples exist in the Azure and Azure-Samples organizations.

### Output

The script generates a CSV file in the results folder for each docset specified in config.json. The output files are tagged with the current date and an incremental number so that if you run the script multiple times you get a series of numbered output files (without complicated timestamps).
