# This script was used to transform the Gridded EPA U.S. Anthropogenic Methane Greenhouse Gas annual dataset from netCDF to Cloud Optimized GeoTIFF (COG) format for display in the Greenhouse Gas (GHG) Center.

import os
import xarray
import re
import pandas as pd
import json
import tempfile
import boto3
from datetime import datetime
from dateutil.relativedelta import relativedelta

session = boto3.session.Session()
s3_client = session.client("s3")
bucket_name = "ghgc-data-store-dev"
FOLDER_NAME = "epa_emissions/monthly_scale"
s3_folder_name = "epa-emissions-monthly-scale-factors"

files_processed = pd.DataFrame(columns=["file_name", "COGs_created"])
for name in os.listdir(FOLDER_NAME):
    xds = xarray.open_dataset(f"{FOLDER_NAME}/{name}", engine="netcdf4")
    xds = xds.assign_coords(lon=(((xds.lon + 180) % 360) - 180)).sortby("lon")
    variable = [var for var in xds.data_vars]
    filename = name.split("/ ")[-1]
    filename_elements = re.split("[_ .]", filename)
    start_time = datetime(int(filename_elements[-2]), 1, 1)

    for time_increment in range(0, len(xds.time)):
        for var in variable:
            filename = name.split("/ ")[-1]
            filename_elements = re.split("[_ .]", filename)
            data = getattr(xds.isel(time=time_increment), var)
            data = data.isel(lat=slice(None, None, -1))
            data.rio.set_spatial_dims("lon", "lat", inplace=True)
            data.rio.write_crs("epsg:4326", inplace=True)
            date = start_time + relativedelta(months=+time_increment)

            # # insert date of generated COG into filename
            filename_elements.pop()
            filename_elements[-1] = date.strftime("%Y%m")
            filename_elements.insert(2, var)
            cog_filename = "_".join(filename_elements)
            # # add extension
            cog_filename = f"{cog_filename}.tif"

            with tempfile.NamedTemporaryFile() as temp_file:
                data.rio.to_raster(
                    temp_file.name,
                    driver="COG",
                )
                s3_client.upload_file(
                    Filename=temp_file.name,
                    Bucket=bucket_name,
                    Key=f"{s3_folder_name}/{cog_filename}",
                )

            files_processed = files_processed._append(
                {"file_name": name, "COGs_created": cog_filename},
                ignore_index=True,
            )

            print(f"Generated and saved COG: {cog_filename}")

with tempfile.NamedTemporaryFile(mode="w+") as fp:
    json.dump(xds.attrs, fp)
    json.dump({"data_dimensions": dict(xds.dims)}, fp)
    json.dump({"data_variables": list(xds.data_vars)}, fp)
    fp.flush()

    s3_client.upload_file(
        Filename=fp.name,
        Bucket=bucket_name,
        Key=f"{s3_folder_name}/metadata.json",
    )
files_processed.to_csv(
    f"s3://{bucket_name}/{s3_folder_name}/files_converted.csv",
)
print("Done generating COGs")