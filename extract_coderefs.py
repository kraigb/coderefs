import csv
import os
import subprocess
import sys
import pathlib
import re
import json

from utilities import *

def extract_coderefs(config, results_folder):
    # Header for error output CSV
    print("Script,Type,Message,Detail,Item")

    for content_set in config["content"]:
        results = []

        # Load up docset configuration
        # TODO: can do more error checking and validation here
        docset = content_set.get("repo")
        folder = os.path.expandvars(content_set.get("path"))  # Expands ${INVENTORY_REPO_ROOT}
        opc_path = os.path.join(folder, content_set.get("opc_folder"), ".openpublishing.publish.config.json")
        docfx_folder = os.path.join(folder, content_set.get("docfx_folder"))
        docfx_path = os.path.join(docfx_folder, "docfx.json")
        disabled = content_set.get("disabled")
        base_url = content_set.get("url")
        exclude_folders = content_set.get("exclude_folders")

        # Determine whether we can or need to process this docset
        if docset is None or base_url is None:
            print(f"extract_coderefs, ERROR, Malformed config entry for docset, Check your config file, {docset}")
            continue

        if disabled:
            print(f"extract_coderefs, INFO, Docset disabled, Skipping, {docset}")
            continue

        if folder is None:
            print(f"extract_coderefs, WARNING, No path for docset, Skipping, {docset}")
            continue

        # Look for the .openpublishing.publish.config.json file, which contains the external repo references
        repo_data = None

        with open(opc_path) as opc:
            data = json.load(opc)
            repo_data = data["dependent_repositories"]

        if repo_data == None:
            print(f'extract_coderefs, WARNING, Docset lacks .openpublishing.publish.config.json file, Skipping, {docset}')
            continue

        # We need fileMetadata from docfx.json to obtain metadata for individual files; the absence,
        # however, is not blocking.
        file_metadata = None        

        with open(docfx_path) as dfx:
            data = json.load(dfx)
            file_metadata = data["build"]["fileMetadata"]

        if file_metadata == None:
            print(f'extract_coderefs, INFO, Docset lacks docfx.json metadata info, , {docset}')


        # We can proceed with this docset
        print(f'extract_coderefs, INFO, Processing docset, {docset}, {folder}')
        
        # Cache the file lists for globs; globbing is a slow operation that we don't want
        # to do with every file!
        desired_metadata = ["ms.author", "ms.reviewer"]
        globs = get_file_metadata_globs(docfx_folder, file_metadata, desired_metadata)

        for root, dirs, files in os.walk(folder):
            # Omit any excluded folders from those we'll process.
            # TODO: does this have any effect?
            for exclusion in exclude_folders:
                if exclusion in dirs:
                    dirs.remove(exclusion)

            for file in files:
                if pathlib.Path(file).suffix != '.md':
                    continue

                full_path = os.path.join(root, file)

                try:
                    content = pathlib.Path(full_path).read_text(errors="replace")
                except UnicodeDecodeError:
                    print(f"extract_coderefs, WARNING, Skipping file that contains non-UTF-8 characters and should be converted, , {full_path}")
                    continue

                # TODO: add --verbose flag to include this message
                # print(f"extract_coderefs, INFO, Processing file, , {full_path}")

                metadata = extract_metadata_fields(content, docfx_folder, full_path, globs, desired_metadata)

                # Content check: if metadata is empty, then the article lacks metadata, but this 
                # isn't a blocking problem.                
                if None == metadata or len(metadata) == 0:
                    print(f"extract_coderefs, WARNING, File contains no metadata, , {full_path}")

                coderefs = find_external_code_refs(content, repo_data)

                if None == coderefs or len(coderefs) == 0:
                    continue

                for ref in coderefs:                
                    if not "file_url" in ref.keys():
                        print(f"extract_coderefs, WARNING, Code reference uses invalid repo path_to_root, {ref['line']}, {full_path}")

                    article_url = base_url + full_path[full_path.find('\\', len(folder) + 1) : -3].replace('\\','/')
                    results.append([docset, full_path, article_url, metadata["ms.author"], metadata["ms.reviewer"], metadata["ms.date"],
                        ref["line"], ref["type"], ref["detail"], ref["file_url"]])


        # Sort the results (by filename, then line number), and save to a .csv file.
        print("extract_coderefs, INFO, Sorting results by filename, , ")        
        # rows.sort(key=lambda row: (row[1], int(row[5])))
        results.sort(key=lambda row: (row[1]))

        # Open CSV output file, which we do before running the searches because
        # we consolidate everything into a single file

        result_filename = get_next_filename(docset.rsplit("/", 1)[-1])
        print(f'extract_coderefs, INFO, Writing CSV results file, , {result_filename}.csv')

        with open(result_filename + '.csv', 'w', newline='', encoding='utf-8') as csv_file:    
            writer = csv.writer(csv_file)
            writer.writerow(["docset", "file", "url", "ms.author", "ms.reviewer", "ms.date", "refLine",
                "refType", "refDetail", "refUrl"])
            writer.writerows(results)

        print(f"extract_coderefs, INFO, Completed CSV results file, , {result_filename}.csv")


if __name__ == "__main__":
    # Get input file arguments, defaulting to folders.txt and terms.txt
    config_file, _ = parse_config_arguments(sys.argv[1:])

    if config_file is None:
        print("Usage: python extract_coderefs.py --config <config_file>")
        sys.exit(2)

    config = None
    with open(config_file, 'r') as config_load:
        config = json.load(config_load)

    if config is None:
        print("extract_coderefs: Could not deserialize config file")
        sys.exit(1)

    repo_folder = os.getenv("CODEREFS_REPO_ROOT")
    
    if repo_folder is None:
        print("extract_coderefs: Set environment variable CODEREFS_REPO_ROOT to your repo root before running the script.")
        sys.exit(1)

    # Run the script in the indicated output folder (or the default)
    results_folder = os.getenv("CODEREFS_RESULTS_FOLDER", "data")

    if not os.path.exists(results_folder):
        os.makedirs(results_folder)

    os.chdir(results_folder)

    extract_coderefs(config, results_folder)
