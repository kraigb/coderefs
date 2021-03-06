import datetime
import getopt
import os
from subprocess import Popen, PIPE
import re
import glob
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime

def get_next_filename(prefix=None):    
    """ Determine the next filename by incrementing 1 above the largest existing file number in the current folder for today's date."""

    from datetime import date
    today = date.today()

    date_pattern = prefix + '_' + str(today)
    files = [f for f in os.listdir('.') if re.match(date_pattern + '-[0-9]+.csv', f)]

    if (len(files) == 0):
        next_num = 1
    else:        
        num_start_index = len(prefix) + 12  # position of "0001" and such
        file_nums = [item[num_start_index:num_start_index + 4] for item in files ]
        next_num = max(int(n) for n in file_nums) + 1

    return "%s-%04d" % (date_pattern, next_num) 


def parse_config_arguments(argv):
    """ Parses an arguments list for take_inventory.py, returning config file name. Any additional arguments after the options are included in the tuple."""
    config_file = "config.json"

    try:
        opts, args = getopt.getopt(argv, 'hH?', ["config="])
    except getopt.GetoptError:
        return (None, None, None)

    for opt, arg in opts:
        if opt in ('-h', '-H', '-?'):
            return (None, None, None)

        if opt in ('--config'):
            config_file = arg
    
    return (config_file, args)


def get_last_local_commit(folder, full_path):
    rel_path = os.path.relpath(full_path, folder)
    # Folder is the repo root; rel_path if the file's relative location.
    # --format=%ci provides simplest output to parse
    p = Popen(f"git log -1 --format=%ci {rel_path}",
        shell=True, cwd=folder, stdout=PIPE, stderr=PIPE, )

    out, err = p.communicate()        

    if 0 == len(out):
        print(f"extract_coderefs, WARNING, Could not obtain last local commit on article, {err.decode('ascii')}, {full_path}")
        return datetime.today().strftime('%m/%d/%Y')

    # Reformat the yyyy-mm-dd commit date to a mm/dd/yyyy date string
    dt = datetime.strptime(out.split()[0].decode('ascii'), "%Y-%m-%d")
    last_local_commit = dt.strftime('%m/%d/%Y')
    return last_local_commit
    

def line_starts_with_metadata(line, path):
    # Output warnings for these (needs to be fixed in the source)
    if line.startswith("??????---"):
        print(f"extract_coderefs, WARNING, File is not utf-8 encoded, , {path}")

    return line.startswith("---") or line.startswith("??????---")

def get_file_metadata_globs(repo_root, file_metadata, desired_fields):
    globs = {}

    for field in desired_fields:
        if field in file_metadata.keys():
            globs[field] = {}

            for spec in file_metadata[field].keys():
                folder_path = os.path.join(repo_root, spec)
                values = {"value": file_metadata[field][spec],
                    "glob": glob.glob(folder_path, recursive=True) }
                globs[field][spec] = values

    return globs


def get_file_metadata(globs, file_path, desired_fields):
    metadata = {}

    # Retrieve metadata of interest that's assigned globally for this file within
    # docfx.json, as represented by the file_metadata that's extracted from the JSON.
    
    for field in desired_fields:
        if field in globs.keys():
            # globs has an entry for this field, so iterate the values to 
            # find a glob that contains the file we're working with.

            for spec in globs[field].keys():
                if file_path in globs[field][spec]["glob"]:
                    # Found a matching path for the file, so record the value. We keep processing
                    # because there may be multiple entries that work, and we always want to use
                    # the last one in the list, which is more specific than earlier globs.
                    metadata[field] = globs[field][spec]["value"]

    return metadata


def extract_metadata_fields(content, repo_root, file_path, globs, desired_fields):    
    saw_first_metadata_header = False
    metadata = {}
    
    for line in iter(content.splitlines(0)):
        # Ignore any comments or blank lines in the metadata header
        if line.startswith("#") or len(line) == 0:
            continue

        if line_starts_with_metadata(line, file_path):
            # If we see the second ---, we've looked at all the header lines.
            if saw_first_metadata_header:
                break

            # Saw the first ---, continue to the next lines
            saw_first_metadata_header = True
            continue
        else:
            if not saw_first_metadata_header:                
                break
        
        # For this line, separate the key and values at the :.
        segments = line.strip().split(":")

        # If we don't have a second segment, there wasn't a : in this line or
        # it's a multi-line value that has line breaks. For simplicity, we just ignore these.
        if len(segments) == 1:
            continue

        # Otherwise, add the key, value pair to the dictionary.
        key = segments[0].strip()
        value = segments[1].strip()
        metadata.update({ key: value })

    # Now that we've processed the metadata in the file, see if we need to add any fields
    # based on docfx.json fileMetadata. We ignore any fields in docfx.json that already exist
    # in metadata, because article values override the docfx.json defaults.

    # We're specifically intrested in only ms.author and ms.reviewer. If we can't find a suitable
    # value for a field, then we use "~" as an indicator for "unknown."
    
    file_metadata_fields = get_file_metadata(globs, file_path, desired_fields)    

    for field in desired_fields:
        if field in file_metadata_fields.keys():
            value = file_metadata_fields[field]
        else:
            value = "~"

        if not field in metadata.keys():
            metadata[field] = value

    return metadata

def strip_quotes(item):
    return item.strip('"')

def code_string_to_dict(code_string):
    result = []

    for sub in code_string.split():
        if "=" in sub:
            result.append(map(strip_quotes, sub.split("=", 1)))

    return dict(result)


def map_repo(source_path, repo_data):
    # source_path is the source property from the :::code statement, within which the 
    for repo in repo_data:
        if source_path == repo["path_to_root"]:
            return repo
    
    return None

def find_external_code_refs(content, repo_data):
    results = []
    line_num = 0

    for line in iter(content.splitlines(0)):        
        line_num += 1
        match = re.match("(?::::code)(.*)(?::::)", line)

        if None == match:
            continue
        
        # Split out all the properties in the :::code string
        props = code_string_to_dict(match.group(1).strip())

        # Here we're interested ONLY in external repo references, which begin with ~/
        # in the source property. If ~/ isn't found, then return None.
        if not "source" in props.keys():
            return None

        source_parts = props["source"].split("/", 2)

        if source_parts[0] != "~":
            return None
        
        if source_parts[1] == "..":
            # We have a ~/.. reference, so we need to split part 2 into two parts.
            parts2 = source_parts[2].split("/", 1)
            source_parts[1] = parts2[0]
            source_parts[2] = parts2[1]
        
        # Now we can build the full return list
        result = {}
        result["line"] = line_num
        result.update(props)
        
        if "id" in props.keys():
            result["type"] = "id"
            result["detail"] = props["id"]
        elif "range" in props.keys():
            result["type"] = "range"
            result["detail"] = "'" + props["range"] + "'"  # Quoted to avoid becoming a date in Excel
        else:
            result["type"] = "whole_file"
            result["detail"] = ""

        # Because we have a ~/ source reference, source_parts[1] is the repo ID and
        # source_parts[2] is the relative path within that repo. To complete the full
        # URL, we make the string: {url}/blob/{branch}/{file} where {url} and {branch} 
        # come from repo_data for the repo ID.
        # 
        # TODO: we ignore branch_mapping as Azure docs don't use this at present.

        repo = map_repo(source_parts[1], repo_data)

        if None != repo:
            result["file_url"] = f'{repo["url"]}/blob/{repo["branch"]}/{source_parts[2]}'

            # Add these for good measure
            result["repo"] = repo["url"]
            result["branch"] = repo["branch"]
            result["file_in_repo"] = source_parts[2]

        results.append(result)

    return results


def get_commit_history(file_url, commit_cache, start_date=None, start_date_local=None):
    # Source URLs are of the form:
    #     https://github.com/{owner}/{repo}/blob/{branch}/{path}
    #     
    # RegEx:
    #     https:\/\/github\.com\/([^\/.]+)*\/([^\/.]+)*\/?\/blob\/([^\/.]+)*\/(.+)
    #     Group 1 is {owner}, Group 2 is {repo}, Group 3 is {branch}, Group 4 is {path}
    #     The extra \/? allows for // before blob, which occurs on occasion in the Azure-docs repo.
    #
    # For example:
    #     https://github.com/Azure-Samples/functions-quickstarts-java/blob/master/functions-add-output-binding-storage-queue/src/main/java/com/function/Function.java
    #
    # Commit history for the file is:
    #     https://api.github.com/repos/{owner}/{repo}/commits?sha={branch}&path={path}
    #
    # For example:
    #     https://api.github.com/repos/Azure-Samples/functions-quickstarts-java/commits?path=functions-add-output-binding-storage-queue/src/main/java/com/function/Function.java
    #    
    # Need to assume public repos (as samples generally are) otherwise we run into auth issues.
    #
    dates = []
    commits_since_start = 0
    commits_since_local = 0
    most_recent = ""
    most_recent_url = ""
    
    if None != start_date:
        # Assume start_date is in ms.date format
        dt_start = datetime.strptime(start_date, "%m/%d/%Y")
    else:
        # Some ridiculously early date for sample code--Microsoft's founding date. :)
        dt_start = datetime(1975, 4, 4)

    if None != start_date_local:
        dt_local = datetime.strptime(start_date_local, "%m/%d/%Y")
    else:
        dt_local = datetime(1975, 4, 4)


    re_url = "https:\/\/github\.com\/([^\/.]+)*\/([^\/.]+)*\/blob\/([^\/.]+)*\/(.+)"
    match = re.match(re_url, file_url)

    if None == match:
        print(f"extract_coderefs, WARNING, GitHub file URL does not match expected pattern, , {file_url}")
        return None
    
    history_url = f"https://api.github.com/repos/{match.group(1)}/{match.group(2)}/commits?sha={match.group(3)}&path={match.group(4)}"

    if not history_url in commit_cache.keys():
        user = os.getenv("GITHUB_USER")
        token = os.getenv("GITHUB_ACCESS_TOKEN")

        response = requests.get(history_url, auth = HTTPBasicAuth(user, token))

        if response.status_code == 200:
            response_data = response.json()
            commit_cache.update({ history_url: response_data })
        else:
            print(f"extract_coderefs, ERROR, Failed to get commit history, {history_url}, {file_url}")
            return None

    else:
        response_data = commit_cache[history_url]

    # Extract all the commit dates that are after the start date (not on the start date, as samples
    # and articles are often updated together).
    for commit in response_data:
        date = commit["commit"]["author"]["date"]
        dt = datetime.strptime(date, "%Y-%m-%dT%H:%M:%SZ")
        
        if "" == most_recent:
            most_recent = dt.strftime('%m/%d/%Y')
            most_recent_url = commit["html_url"]

        if (dt.date() > dt_start.date()):
            commits_since_start += 1

        if (dt.date() > dt_local.date()):
            commits_since_local += 1

    return {
        "commits_since_start": commits_since_start,
        "commits_since_local": commits_since_local,
        "most_recent": most_recent,
        "most_recent_url": most_recent_url
    }    
