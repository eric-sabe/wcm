#!/bin/bash

# Usage: ./update_remotes.sh <old_org> <new_user> <directory_with_repos>
# Example: ./update_remotes.sh my-old-org eric-sabe ~/git/my-repos

OLD_ORG=$1
NEW_USER=$2
TARGET_DIR=$3

if [ -z "$OLD_ORG" ] || [ -z "$NEW_USER" ] || [ -z "$TARGET_DIR" ]; then
    echo "Usage: $0 <old_org> <new_user> <directory_with_repos>"
    exit 1
fi

if [ ! -d "$TARGET_DIR" ]; then
    echo "Error: Directory $TARGET_DIR does not exist."
    exit 1
fi

echo "Scanning $TARGET_DIR for git repositories..."

# Find all .git directories and iterate over their parent directories
find "$TARGET_DIR" -type d -name ".git" | while read -r gitdir; do
    repo_dir=$(dirname "$gitdir")
    
    # Get the current origin URL
    current_url=$(git -C "$repo_dir" remote get-url origin 2>/dev/null)
    
    if [ -n "$current_url" ]; then
        # Check if the URL contains the old organization
        if [[ "$current_url" == *"$OLD_ORG"* ]]; then
            # Replace the old org with the new user in the URL
            new_url="${current_url/$OLD_ORG/$NEW_USER}"
            
            echo "Updating remote for: $repo_dir"
            echo "  Old: $current_url"
            echo "  New: $new_url"
            
            # Update the remote URL
            git -C "$repo_dir" remote set-url origin "$new_url"
        fi
    fi
done

echo "Done!"
