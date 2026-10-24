from io import BytesIO
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

# data folder
# .resolve() converts a path into an absolute path, for prevention of potential buggs
# .parent then stores the parent folder
PROJECT_DIR = Path(__file__).resolve().parent

# creates the paths important folders
DATA_DIR = PROJECT_DIR / "data" / "raw"

# creates the folders. exist_ok = True ensures that it isn't a problem if the folder already exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# download link to the current f1db data
URL = "https://github.com/f1db/f1db/releases/latest/download/f1db-csv.zip"

# These are the files which are currently used
FILES = [
    "f1db-races.csv",
    "f1db-races-race-results.csv",
    "f1db-races-qualifying-results.csv",
]

# opens the URL, if it takes longer then 60s it will be aborted
# as response declares how the server response is named: here its name is "response"
with urlopen(URL, timeout=60) as response:
    zip_data = response.read()

# BytesIO makes the response.read() information which is stored in bytes readable as zip file
# ZipFile then saves the zip-archive under the name "archive"
# finally the for loop then extracts the files we declared as used in the FILES path
# .write_bytes() stores the content in the declared name, if a file is alreasy stored under this exact name it will be overwritten
with ZipFile(BytesIO(zip_data)) as archive:
    for filename in FILES:
        contents = archive.read(filename)
        destination = DATA_DIR / filename
        destination.write_bytes(contents)
        print(f"Saved: {filename}")

print("Update complete")
