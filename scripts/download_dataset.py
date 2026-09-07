import os
import sys
import git
import yaml
import shutil
from pathlib import Path

def download_dataset(config_path="configs/config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    repo_url = config["dataset"]["repository_url"]
    raw_dir = Path(config["dataset"]["raw_dir"])
    train_rel = config["dataset"]["train_file"]
    dev_rel = config["dataset"]["dev_file"]

    raw_dir.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Dataset target directory: {raw_dir.resolve()}")

    if raw_dir.exists() and (raw_dir / train_rel).exists() and (raw_dir / dev_rel).exists():
        print(f"Dataset already acquired at {raw_dir}")
    else:
        if raw_dir.exists():
            print(f"Directory {raw_dir} exists but files are incomplete. Re-cloning...")
            shutil.rmtree(raw_dir)
        
        print(f"Cloning repository: {repo_url} -> {raw_dir}")
        try:
            git.Repo.clone_from(repo_url, raw_dir)
            print("Git clone successful.")
        except Exception as e:
            print(f"ERROR: Failed to clone repository {repo_url}: {e}")
            sys.exit(1)
    
    # Validate files
    train_path = raw_dir / train_rel
    dev_path = raw_dir / dev_rel

    if not train_path.exists():
        print(f"ERROR: Expected train dataset file not found at: {train_path}")
        sys.exit(1)
        
    if not dev_path.exists():
        print(f"ERROR: Expected dev dataset file not found at: {dev_path}")
        sys.exit(1)

    print("\n--- Downloaded Dataset Files ---")
    downloaded_files = list(raw_dir.rglob("*"))
    for file_path in downloaded_files:
        if file_path.is_file() and ".git" not in file_path.parts:
            print(f"  [FILE] {file_path.relative_to(raw_dir)} ({file_path.stat().st_size} bytes)")

    print("\nDataset acquisition completed and verified successfully.")
    return True

if __name__ == "__main__":
    download_dataset()
