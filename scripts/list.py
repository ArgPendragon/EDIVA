import os
import sys
import re

def numerical_sort_key(filename):
    """Extracts numbers from the filename for proper numerical sorting."""
    numbers = re.findall(r'\d+', filename)  # Find all numbers in the filename
    return [int(n) for n in numbers] if numbers else [0]  # Convert to integers

def list_files(folder_path, show_empty=False):
    """Lists all files in a folder, sorts them numerically, and saves to a .txt file."""
    if not os.path.exists(folder_path):
        print("Folder not found!")
        return

    file_list = []
    for file_name in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file_name)
        
        if os.path.isfile(file_path):
            size_kb = os.path.getsize(file_path) / 1024  # Convert bytes to KB
            if show_empty and size_kb >= 0.5:
                continue  # Skip files that are 0.5 KB or larger
            file_list.append((file_name, size_kb))

    # Sort files numerically
    file_list.sort(key=lambda x: numerical_sort_key(x[0]))

    # Define output file path
    output_file = os.path.join(folder_path, "file_list.txt")

    # Write to file
    with open(output_file, "w", encoding="utf-8") as f:
        for file_name, size_kb in file_list:
            f.write(f"{file_name} - {size_kb:.2f} KB\n")

    print(f"File list saved to: {output_file}")

# Check if the folder path is provided
if len(sys.argv) < 2:
    print("Usage: python script.py <folder_path> [empty]")
else:
    folder_path = sys.argv[1]
    show_empty = len(sys.argv) > 2 and sys.argv[2].lower() == "empty"
    list_files(folder_path, show_empty)
