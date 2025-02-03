# Segmentation Labeling Tool

A command-line tool for comparing and labeling the quality of two different segmentation methods on medical images. The tool displays segmentations side-by-side using Freeview and collects structured feedback about their relative quality.

## Features

- Interactive comparison of two segmentation methods
- Randomized presentation to prevent bias
- Automatic focus on areas with significant differences
- Structured feedback collection including:
  - Better performing method
  - Confidence level
  - Magnitude of differences
  - Segmentation failure detection
  - Custom comments

## Usage
```bash
python labeling_tool.py --method1 <method1> --method2 <method2> [options]
```


### Required Arguments

- `-m1, --method1`: Name of the first segmentation method
- `-m2, --method2`: Name of the second segmentation method
- `-o, --output_file`: Path to save the CSV results
- `-i, --input_data`: CSV file containing input data with columns: "subjectID", "image", "method1", "method2"
- `--diff_maps_dir`: Directory containing difference maps

### Optional Arguments

- `--user`: Name of the labeler (defaults to system username)
- `--fs`: Path to FreeSurfer home directory

## Output

Results are saved in CSV format with the following information:
- Subject ID
- Method names
- Better performing method
- Confidence level (random/uncertain/certain)
- Difference strength (none/marginal/moderate/substantial)
- Segmentation failures
- User comments
- Labeler name
- Time taken
- Number of differences

## Requirements

- FreeSurfer
- Python 3.x
- nibabel
- pandas
- tqdm
- xdotool (optional, for window management)
