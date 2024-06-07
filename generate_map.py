import requests
import folium
import logging
from google.cloud import storage
from datetime import datetime
import os

# Configure logging
logging.basicConfig(level=logging.INFO)

def get_env_variable(name):
    """Fetch and return the value of the environment variable."""
    value = os.environ.get(name)
    if not value:
        logging.error(f'Error: {name} environment variable not set.')
        raise EnvironmentError(f'{name} environment variable not set.')
    return value

def fetch_total_pages(url, headers):
    """Fetch the total number of pages from the API."""
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        logging.error(f'Error: API request failed with status code {response.status_code}')
        raise Exception(f'API request failed with status code {response.status_code}')
    return response.json().get("total_pages", 0)

def fetch_points(url, headers, page):
    """Fetch points data for a specific page."""
    params = {'page': page}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        logging.error(f'Error: API request failed with status code {response.status_code}')
        raise Exception(f'API request failed with status code {response.status_code}')
    return response.json().get("items", [])

def add_points_to_map(points, my_map, air_quality_index_to_color_code):
    """Add points to the folium map with appropriate color coding."""
    for point in points:
        if point.get("air_index_level") is not None:
            color_code = air_quality_index_to_color_code.get(point["air_index_level"], "gray")
            air_quality_index = point["air_index_level"]
            folium.Circle(
                location=[point['location']['latitude'], point['location']['longitude']],
                radius=750,
                fill_opacity=0.6,
                fill_color=color_code,
                stroke=False,
                tooltip=air_quality_index
            ).add_to(my_map)

def upload_to_gcs(bucket_name, gcs_object_name, file_path, content_type):
    """Upload a file to Google Cloud Storage."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(gcs_object_name)
    blob.upload_from_filename(file_path, content_type=content_type)
    logging.info(f'HTML file uploaded to GCS: gs://{bucket_name}/{gcs_object_name}')

def generate_map(request):
    # Fetch API token
    token = get_env_variable('INPOST_API_TOKEN')

    # API location and auth
    url = "https://api.inpost.pl/v1/points"
    headers = {"Authorization": f"Bearer {token}"}

    # Create a folium map centered on Poland
    map_center = [52, 19]
    my_map = folium.Map(location=map_center, zoom_start=7)

    # Color coding for different air quality indexes from points
    air_quality_index_to_color_code = {
        "VERY_GOOD": "green",
        "GOOD": "lightgreen",
        "SATISFACTORY": "orange",
        "MODERATE": "red",
        "BAD": "darkred",
        "VERY_BAD": "black"
    }

    # Fetch total number of pages
    total_pages = fetch_total_pages(url, headers)

    # Process each page and add points to the map
    for i in range(1, total_pages + 1):
        points = fetch_points(url, headers, i)
        add_points_to_map(points, my_map, air_quality_index_to_color_code)

    # Add the current date as a text label as the title
    current_date = datetime.now().strftime("%H:%M %d.%m.%Y")
    title_html = f'<h1 style="position:absolute;z-index:100000;left:35vw">Dane pobrano o godzinie {current_date}</h1>'
    my_map.get_root().html.add_child(folium.Element(title_html))

    # Save the map as a (/tmp required by GCF) HTML file
    output_file_path = "/tmp/index.html"
    my_map.save(output_file_path)

    # Upload file to GCS
    bucket_name = "www.inpair.pl"
    gcs_object_name = "index.html"
    content_type = "text/html"

    try:
        upload_to_gcs(bucket_name, gcs_object_name, output_file_path, content_type)
    except Exception as e:
        logging.error(f'An error occurred: {e}')
        return {
            'statusCode': 500,
            'body': f'An error occurred: {e}'
        }

    return {
        'statusCode': 200,
        'body': 'HTML file uploaded to GCS successfully.'
    }
