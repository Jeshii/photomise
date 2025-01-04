#!/usr/bin/env python3

import argparse
import exifread
from geopy.geocoders import Nominatim

def extract_gps_info(image_path):
    with open(image_path, 'rb') as f:
        tags = exifread.process_file(f)
        
        # Extract GPS data
        gps_latitude = tags.get('GPS GPSLatitude')
        gps_latitude_ref = tags.get('GPS GPSLatitudeRef')
        gps_longitude = tags.get('GPS GPSLongitude')
        gps_longitude_ref = tags.get('GPS GPSLongitudeRef')
        
        if gps_latitude and gps_latitude_ref and gps_longitude and gps_longitude_ref:
            lat = convert_to_degrees(gps_latitude)
            if gps_latitude_ref.values[0] != 'N':
                lat = -lat
            lon = convert_to_degrees(gps_longitude)
            if gps_longitude_ref.values[0] != 'E':
                lon = -lon
            return (lat, lon)
        else:
            return None

def convert_to_degrees(value):
    d = float(value.values[0].num) / float(value.values[0].den)
    m = float(value.values[1].num) / float(value.values[1].den)
    s = float(value.values[2].num) / float(value.values[2].den)
    return d + (m / 60.0) + (s / 3600.0)

def main(args):
    gps_info = extract_gps_info(args.photo_file)
    if gps_info:
       print(f"Latitude: {gps_info[0]}, Longitude: {gps_info[1]}")
    else:
       print("No GPS info found.")

    geolocator = Nominatim(user_agent=args.user_agent)

    location = geolocator.reverse((gps_info[0], gps_info[1]))

    # Output the address
    if location:
        print("Locations:", location.raw)
    else:
        print("No locations returned for these coordinates.")

def parse_args():
    description = "A script to find locations that match photo location metadata."

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter, 
        description=description
    )
    parser.add_argument("photo_file", help="The file location of a photo to analyze")
    parser.add_argument("user_agent", help="The user agent to use for Nominatim")
    args = parser.parse_args()

    return args

# This is for running the script once deployed
def entry():
    try:
        args = parse_args()  # Parse the arguments here
        main(args)
    except KeyboardInterrupt:
        print("Exiting...")


# This is for running the script during development
if __name__ == "__main__":
    entry()