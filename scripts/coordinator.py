import json

def process_record(record):
    # Check if "caption_coordinates" exists and has a value.
    if record.get("caption_coordinates"):
        # Delete the other two fields if they exist.
        record.pop("internal_caption_coordinates", None)
        record.pop("external_caption_coordinates", None)
    else:
        # No valid "caption_coordinates" is present.
        # Prioritize internal_caption_coordinates if available.
        if record.get("internal_caption_coordinates"):
            record["caption_coordinates"] = record["internal_caption_coordinates"]
        elif record.get("external_caption_coordinates"):
            record["caption_coordinates"] = record["external_caption_coordinates"]
        
        # Remove both fields regardless, so only caption_coordinates remains.
        record.pop("internal_caption_coordinates", None)
        record.pop("external_caption_coordinates", None)
    
    return record

def main():
    input_filename = "D:/cardotest/ExtractedImages/1God/bookindexold.json"   # Change to your input JSON file path
    output_filename = "D:/cardotest/ExtractedImages/1God/bookindex.json" # Change to your desired output file path

    # Load the JSON data from the file.
    with open(input_filename, "r") as infile:
        data = json.load(infile)

    # Process each record in the JSON data.
    processed_data = [process_record(record) for record in data]

    # Write the updated JSON data to the output file.
    with open(output_filename, "w") as outfile:
        json.dump(processed_data, outfile, indent=4)

if __name__ == "__main__":
    main()
