import psutil
import os
import argparse

def find_locking_processes(path: str):
    """Find and list all processes that have open file handles within a given path."""
    abs_path = os.path.abspath(path)
    locking_processes = []

    print(f"Searching for processes with open files in: {abs_path}")

    for proc in psutil.process_iter(['pid', 'name', 'open_files']):
        try:
            if proc.info['open_files']:
                for file in proc.info['open_files']:
                    if os.path.abspath(file.path).startswith(abs_path):
                        if proc.pid not in [p['pid'] for p in locking_processes]:
                            locking_processes.append({
                                'pid': proc.pid,
                                'name': proc.name(),
                                'path': file.path
                            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    if locking_processes:
        print("\nFound processes locking the geodatabase:")
        for p in locking_processes:
            print(f"  - PID: {p['pid']}, Name: {p['name']}, File: {p['path']}")
    else:
        print("\nNo processes found locking the geodatabase.")
        
    return [p['pid'] for p in locking_processes]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find processes locking a geodatabase directory.")
    parser.add_argument(
        "--gdb_path",
        default="./data/source/DTM.gdb",
        help="Path to the geodatabase directory."
    )
    
    args = parser.parse_args()
    find_locking_processes(args.gdb_path) 