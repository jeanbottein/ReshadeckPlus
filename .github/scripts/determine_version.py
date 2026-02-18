import os
import sys
import re
import subprocess

def get_latest_remote_tag():
    try:
        # Fetch references from remote
        output = subprocess.check_output(["git", "ls-remote", "--tags", "origin"], stderr=subprocess.DEVNULL).decode().strip()
    except subprocess.CalledProcessError:
        print("Warning: Could not fetch remote tags. Falling back to v0.0.0", file=sys.stderr)
        return "v0.0.0"

    versions = []
    
    for line in output.split('\n'):
        # line: SHA\trefs/tags/v1.0.0
        parts = line.split()
        if len(parts) < 2:
            continue
            
        ref = parts[1]
        
        # We only care about refs/tags/v...
        # and ignore peeled tags ^{}
        if ref.endswith('^{}'):
             continue
             
        tag_name = ref.replace('refs/tags/', '')
        
        # Check strict vX.Y.Z format
        match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", tag_name)
        if match:
            major, minor, patch = map(int, match.groups())
            versions.append(((major, minor, patch), tag_name))
            
    if not versions:
        return "v0.0.0"
        
    # Sort by tuple (major, minor, patch) descending
    versions.sort(key=lambda x: x[0], reverse=True)
    
    latest_tag = versions[0][1]
    return latest_tag

def ensure_tag_exists_locally(tag):
    if tag == "v0.0.0": return
    
    # Check if exists
    try:
        subprocess.check_call(["git", "rev-parse", "--verify", tag], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        # Fetch it explicitly
        print(f"Tag {tag} not found locally. Fetching from origin...", file=sys.stderr)
        try:
            subprocess.check_call(["git", "fetch", "origin", f"refs/tags/{tag}:refs/tags/{tag}"], stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            print(f"Failed to fetch tag {tag}", file=sys.stderr)


def get_commits_since(ref):
    if not ref or ref == "v0.0.0":
        # If no ref, get all commits
        commit_range = "HEAD"
    else:
        commit_range = f"{ref}..HEAD"
    
    # Format: hash subject body
    # We use a separator to parse easily
    separator = "|||"
    cmd = ["git", "log", "--format=%h%n%s%n%b" + separator, commit_range]
    try:
        output = subprocess.check_output(cmd).decode().strip()
        if not output:
            return []
        
        commits = []
        for raw_commit in output.split(separator):
            if not raw_commit.strip():
                continue
            parts = raw_commit.strip().split("\n", 2)
            hash_id = parts[0]
            subject = parts[1]
            body = parts[2] if len(parts) > 2 else ""
            commits.append({"hash": hash_id, "subject": subject, "body": body})
        return commits
    except subprocess.CalledProcessError:
        return []

def parse_commit_type(subject, body):
    # Conventional Commits regex
    # type(scope)!: subject
    # type: subject
    match = re.match(r"^(\w+)(?:\(([^)]+)\))?(!?):\s+(.*)", subject)
    if not match:
        return None, False, subject

    ctype = match.group(1)
    is_breaking = match.group(3) == "!"
    description = match.group(4)

    # Check for BREAKING CHANGE in body
    if "BREAKING CHANGE:" in body:
        is_breaking = True

    return ctype, is_breaking, description

def determine_version(current_version, commits):
    # current_version format: vX.Y.Z
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", current_version)
    if not match:
        print(f"Error: Invalid version format {current_version}", file=sys.stderr)
        sys.exit(1)
        
    major, minor, patch = map(int, match.groups())
    
    should_release = False
    increment_major = False
    increment_minor = False
    increment_patch = False
    
    changelog = []

    for commit in commits:
        ctype, is_breaking, description = parse_commit_type(commit["subject"], commit["body"])
        
        # Default behavior for non-conventional commits: treat as 'misc' -> minor? or patch?
        # User requirement: "move to a new intermediate version otherwise"
        # Since we can't reliably know, maybe safer to assume minor if it's not strictly chore/fix?
        # But if it doesn't match conventional, we might just ignore or treat as minor.
        # Let's verify strict compliance. If not compliant, maybe treat as 'chore'?
        # The prompt implies looking at prefix.
        
        # If parse failed (None), checking if it has a prefix effectively manually
        if not ctype:
            # Check for simple prefix manually if regex failed (e.g. "fix: something" without scope)
            # The regex `^(\w+)(?:\(([^)]+)\))?(!?):\s+(.*)` handles `fix: ...`
            # So if it failed, it's likely "merge branch..." or "random message"
            # We will ignore commits that don't follow the pattern or maybe default to patch?
            # User said: "move to a new intermediate version otherwise" -> implies default is MINOR.
            # But let's look at "skip if doc: or ci:".
            
            # Simple fallback check
            clean_sub = commit["subject"].strip()
            if clean_sub.startswith("BREAKING CHANGE:"):
                is_breaking = True
                ctype = "feat" # treat as feature
            else:
                 # Check strict prefixes based on user list
                 # "skip if its a doc: or ci: commit"
                 parts = clean_sub.split(":", 1)
                 if len(parts) == 2:
                     c_prefix = parts[0].strip()
                     if c_prefix in ["docs", "doc", "ci"]:
                         continue # Skip
                     if c_prefix in ["chore", "fix"]:
                         ctype = c_prefix
                         description = parts[1].strip()
                     else:
                        # "otherwise"
                         ctype = "feat" # Default to intermediate
                         description = parts[1].strip()
                 else:
                     # no colon, treat as otherwise -> minor?
                     # or maybe ignore? Usually standard is to ignore unstructured commits.
                     # But "move to a new intermediate version otherwise" suggests default is minor.
                     ctype = "misc"
                     description = clean_sub

        if ctype in ["docs", "doc", "ci"]:
            continue

        should_release = True
        changelog.append(f"- {commit['subject']}")

        if is_breaking:
            increment_major = True
        elif ctype in ["chore", "fix"]:
            increment_patch = True
        else:
            # "move to a new intermediate version otherwise"
            increment_minor = True

    if not should_release:
        return current_version, False, ""

    if increment_major:
        major += 1
        minor = 0
        patch = 0
    elif increment_minor:
        minor += 1
        patch = 0
    elif increment_patch:
        patch += 1
    
    new_version = f"{major}.{minor}.{patch}"
    return new_version, True, "\n".join(changelog)

def main():
    current_tag = get_latest_remote_tag()
    
    # Ensure tag starts with v for parsing
    if not current_tag:
        current_tag = "v0.0.0"
    if not current_tag.startswith("v"):
        current_tag = "v" + current_tag

    # If we found a real tag, ensure we have it locally for git log
    if current_tag != "v0.0.0":
        ensure_tag_exists_locally(current_tag)
        
    commits = get_commits_since(current_tag)
    new_version, should_release, changelog = determine_version(current_tag, commits)
    
    # Output for GitHub Actions
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.getenv("GITHUB_OUTPUT"), "a") as f:
            f.write(f"new_version={new_version}\n")
            f.write(f"should_release={str(should_release).lower()}\n")
            # Escape newlines for multiline output
            changelog = changelog.replace("%", "%25").replace("\n", "%0A").replace("\r", "%0D")
            f.write(f"changelog={changelog}\n")
    else:
        print(f"New Version: {new_version}")
        print(f"Should Release: {should_release}")
        print("Changelog:")
        print(changelog)

if __name__ == "__main__":
    main()
