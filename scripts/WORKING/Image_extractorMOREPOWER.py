import os

# Folder where your .res file is located
folder_path = "C:/Users/Jack/Documents/My Kindle Content/B094113LL4_EBOK"  # Update with actual path
output_folder = "C:/Cardotest/ExtractedImages/5Newborn"  # Change to where you want the images saved

# Ensure output directory exists
os.makedirs(output_folder, exist_ok=True)

# Function to extract all images
def extract_images(file_path):
    with open(file_path, "rb") as f:
        data = f.read()

    image_count = 0  # Counter for naming extracted images
    offset = 0

    while True:
        # Search for different image format signatures
        jpg_start = data.find(b'\xFF\xD8\xFF', offset)  # JPEG
        png_start = data.find(b'\x89PNG', offset)  # PNG
        webp_start = data.find(b'RIFF', offset)  # WebP (starts with RIFF)
        bmp_start = data.find(b'BM', offset)  # BMP (Windows Bitmap)

        # Determine which image format appears first
        starts = [(jpg_start, "jpg"), (png_start, "png"), (webp_start, "webp"), (bmp_start, "bmp")]
        starts = [(s, ext) for s, ext in starts if s != -1]
        
        if not starts:
            break  # No more images found
        
        start, extension = min(starts)  # Pick the first detected image format

        # Try to find the end of the image
        if extension == "jpg":
            end = data.find(b'\xFF\xD9', start) + 2  # JPEG end marker
        elif extension == "png":
            end = data.find(b'\x49\x45\x4E\x44\xAE\x42\x60\x82', start) + 8  # PNG end marker
        elif extension == "webp":
            end = data.find(b'WEBP', start) + 30_000  # Estimate WebP size
        elif extension == "bmp":
            end = start + int.from_bytes(data[start + 2:start + 6], "little")  # BMP header defines size

        if end == -1 or end <= start:
            print(f"⚠ Warning: Could not determine end of {extension} image at offset {start}")
            break  # Stop if we can't determine the end

        # Save the extracted image
        image_count += 1
        image_filename = os.path.join(output_folder, f"image_{image_count}.{extension}")
        with open(image_filename, "wb") as img_file:
            img_file.write(data[start:end])

        print(f" Extracted: {image_filename}")
        offset = end  # Move to the next possible image

    print(f"\n Extraction complete! {image_count} images saved in {output_folder}")

# Find the .res file and extract images
for file in os.listdir(folder_path):
    if file.endswith(".res"):
        res_file_path = os.path.join(folder_path, file)
        print(f" Processing: {res_file_path}")
        extract_images(res_file_path)
