#!/bin/bash

PACKAGE_DIR=build
ZIP_NAME=log-processor.zip

cd ../../../../../container

rm $ZIP_NAME
rm -r $PACKAGE_DIR
pip3 install --target $PACKAGE_DIR -r requirements.txt
cd $PACKAGE_DIR
zip -r ../$ZIP_NAME .
cd ../
zip -g $ZIP_NAME log_processor.py

mv $ZIP_NAME ../terraform/modules/regional/modules/lambda-stack
