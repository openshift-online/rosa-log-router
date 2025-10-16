#!/bin/bash

# Accept optional output path as first argument
# Default to current behavior (regional module location)
OUTPUT_PATH="${1:-../terraform/modules/regional/modules/lambda-stack/log-processor.zip}"

PACKAGE_DIR=build
ZIP_NAME=log-processor.zip

# Get script directory to ensure relative paths work correctly
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Change to container directory (relative to repo root)
cd "$SCRIPT_DIR/../../../../../container"

# Clean up old builds
rm -f $ZIP_NAME
rm -rf $PACKAGE_DIR

# Install dependencies
pip3 install --target $PACKAGE_DIR -r requirements.txt

# Create zip
cd $PACKAGE_DIR
zip -r ../$ZIP_NAME .
cd ../
zip -g $ZIP_NAME log_processor.py

# Move to output location
# If OUTPUT_PATH is absolute, use it directly
# If relative, resolve it relative to container directory
if [[ "$OUTPUT_PATH" = /* ]]; then
    mv $ZIP_NAME "$OUTPUT_PATH"
else
    mv $ZIP_NAME "../$OUTPUT_PATH"
fi

echo "✅ Built $ZIP_NAME and moved to $OUTPUT_PATH"
