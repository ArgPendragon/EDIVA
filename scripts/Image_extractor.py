import os

# Folder where your .res file is located
folder_path = "C:/Users/Jack/Documents/My Kindle Content/B094113LL4_EBOK"  # Update with your actual path
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
        # Search for JPEG start marker (FF D8 FF)
        jpg_start = data.find(b'\xFF\xD8\xFF', offset)
        png_start = data.find(b'\x89PNG', offset)

        # Determine which image format is next
        if jpg_start == -1 and png_start == -1:
            break  # No more images found

        if jpg_start != -1 and (jpg_start < png_start or png_start == -1):
            start = jpg_start
            extension = "jpg"
        else:
            start = png_start
            extension = "png"

        # Try to find the end of the image
        if extension == "jpg":
            end = data.find(b'\xFF\xD9', start)  # JPEG end marker
            end += 2 if end != -1 else 0
        else:  # PNG
            end = data.find(b'\x49\x45\x4E\x44\xAE\x42\x60\x82', start)  # PNG end marker
            end += 8 if end != -1 else 0

        if end == -1:
            print(f"Warning: Could not determine end of {extension} image at offset {start}")
            break  # Stop if we can't determine where the image ends

        # Save the extracted image
        image_count += 1
        image_filename = os.path.join(output_folder, f"image_{image_count}.{extension}")
        with open(image_filename, "wb") as img_file:
            img_file.write(data[start:end])

        print(f"Extracted: {image_filename}")
        offset = end  # Move to the next possible image

    print(f"\n✅ Extraction complete! {image_count} images saved in {output_folder}")

# Find the .res file and extract images
for file in os.listdir(folder_path):
    if file.endswith(".res"):
        res_file_path = os.path.join(folder_path, file)
        print(f"Processing: {res_file_path}")
        extract_images(res_file_path)