#!/usr/bin/env python3
"""Fix all absolute imports to relative imports"""
import os
import re

def fix_imports_in_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # For files in src/ directory (not in subdirs)
    if filepath.count(os.sep) == 1 and 'src' + os.sep in filepath:
        content = re.sub(r'from src\.', 'from .', content)
    # For files in src/api/v1/ directory  
    elif 'api' + os.sep + 'v1' in filepath:
        content = re.sub(r'from src\.', 'from ...', content)
    # For other subdirectories
    elif filepath.count(os.sep) > 1:
        content = re.sub(r'from src\.', 'from ..', content)
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'Fixed imports in {filepath}')

# Find all Python files with src. imports
for root, dirs, files in os.walk('src'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            fix_imports_in_file(filepath)

print('All imports fixed')