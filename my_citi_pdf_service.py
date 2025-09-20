import os
import requests
from bs4 import BeautifulSoup
import time
import PyPDF2
import re
import threading
from concurrent.futures import ThreadPoolExecutor
import fitz  # PyMuPDF

class MyCitiPDFService:
    def __init__(self, download_folder='myciti_pdfs'):
        self.url = 'https://www.myciti.org.za/en/timetables/route-stop-station-timetables/'
        self.download_folder = download_folder
        os.makedirs(self.download_folder, exist_ok=True)

    def fetch_route_links(self):
        """Fetches all route links from the website."""
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(self.url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        routes = soup.find_all('div', class_='route column')
        
        route_info = [{
            'route_code': route.find('span', class_='route-item-label').text.strip(),
            'route_name': route.find('span', class_='route-item-title').text.strip()
        } for route in routes if route.find('a', href=True)]
        
        return route_info

    def download_route_pdf(self, route_code):
        """Downloads the timetable PDF for a specific route."""
        pdf_url = f'https://www.myciti.org.za/docs/route-timetables/{route_code}-timetable.pdf'
        pdf_name = f"{route_code}-timetable.pdf"
        pdf_path = os.path.join(self.download_folder, pdf_name)
        
        response = requests.get(pdf_url, stream=True)
        if response.status_code == 200:
            with open(pdf_path, 'wb') as pdf_file:
                for chunk in response.iter_content(chunk_size=1024):
                    pdf_file.write(chunk)
            print(f"Downloaded {pdf_name}")
        else:
            print(f"Failed to download {pdf_name}")

    def download_all_pdfs(self):
        """Downloads all the timetables for all routes."""
        routes = self.fetch_route_links()
        for route in routes:
            print(f"Fetching timetable for route: {route['route_name']} ({route['route_code']})")
            self.download_route_pdf(route['route_code'])

class TimetableExtractor:
    def __init__(self, download_folder='myciti_pdfs'):
        self.download_folder = download_folder
        self.routes_data = []
        self.lock = threading.Lock()

    def extract_pdf_data(self, pdf_path):
        """Extracts text from a PDF using PyMuPDF with parallel processing for faster execution."""
        with fitz.open(pdf_path) as doc:
            with ThreadPoolExecutor() as executor:
                page_texts = list(executor.map(lambda page: page.get_text("blocks"), doc))

        # Flatten and join all extracted text blocks
        text = "\n".join(["\n".join(block[4] for block in page if len(block) > 4) for page in page_texts])
        return text

    def parse_timetable_data(self, pdf_text):
        """Parses timetable data from the extracted PDF text."""
        timetable_data = {}
        route_pattern = re.compile(r'(\w+):\s([A-Za-z\s\-]+)')
        day_pattern = re.compile(r'(MONDAYS TO FRIDAYS|SATURDAYS|SUNDAYS AND PUBLIC HOLIDAYS)')
        stop_pattern = re.compile(r'([A-Za-z\s\-]+)\s([\d\s:]+)')

        # Route and description
        route_match = route_pattern.search(pdf_text)
        if route_match:
            timetable_data['route'] = {
                'code': route_match.group(1),
                'description': route_match.group(2)
            }

        # Days and stops
        for day_match in day_pattern.finditer(pdf_text):
            day = day_match.group(1)
            timetable_data[day] = []
            day_text_start = pdf_text[day_match.end():]
            for stop_match in stop_pattern.finditer(day_text_start):
                stop_name = stop_match.group(1).strip()
                times = stop_match.group(2).strip().split()
                timetable_data[day].append({'stop': stop_name, 'times': times})

        return timetable_data
    
    def display_timetable(self, route_code):
        """Extracts, parses, and displays timetable data for the given route."""
        pdf_name = f"{route_code}-timetable.pdf"
        pdf_path = os.path.join(self.download_folder, pdf_name)

        if os.path.exists(pdf_path):
            print(f"Extracting and parsing data from {pdf_name}...")
            pdf_text = self.extract_pdf_data(pdf_path)
            timetable_data = self.parse_timetable_data(pdf_text)
            self.print_timetable(timetable_data)
        else:
            print(f"PDF file for route {route_code} does not exist.")

    def print_timetable(self, timetable_data):
        """Prints the structured timetable data."""
        print(f"Route: {timetable_data['route']['code']} - {timetable_data['route']['description']}\n")
        for day, stops in timetable_data.items():
            if day == 'route':
                continue
            print(f"Day: {day}")
            for stop_data in stops:
                print(f"  Stop: {stop_data['stop']}")
                print(f"    Times: {', '.join(stop_data['times'])}")
            print()

    def list_downloaded_pdfs(self):
        """Lists all downloaded PDF files."""
        return [f for f in os.listdir(self.download_folder) if os.path.isfile(os.path.join(self.download_folder, f))]
    
    def getAllRoutes(self):
        """Returns a list of all downloaded PDF files."""
        return self.list_downloaded_pdfs()
    
    def threadingInRoutes(self, start, end, all_route_paths, threadNum):
        print(f"Thread {threadNum} started")
        start_time = time.time()  # Start timer
        routes_data_found = []
        for routeIndex in range(start, end):
            pdf_path = os.path.join(self.download_folder, all_route_paths[routeIndex])
            pdf_text = self.extract_pdf_data(pdf_path)
            timetable_data = self.parse_timetable_data(pdf_text)
            routes_data_found.append(timetable_data)
        end_time = time.time()  # End timer
        execution_time = end_time - start_time
        print(f"Thread {threadNum} finished with {len(routes_data_found)} routes data found. Took {execution_time}s")
        # Locking ensures only one thread can update results at a time
        with self.lock:
            self.routes_data.extend(routes_data_found)

    def getAllRoutesData(self):
        """Extracts and returns structured timetable data for all routes using ThreadPoolExecutor."""
        self.routes_data = []
        all_route_paths = self.getAllRoutes()
        
        print(f"Processing {len(all_route_paths)} routes...")
        
        num_threads = max(1, len(all_route_paths) // 4)  # Ensure at least 1 thread
        start_time = time.time()

        def process_route(pdf_path):
            pdf_text = self.extract_pdf_data(pdf_path)
            return self.parse_timetable_data(pdf_text)

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            results = executor.map(process_route, [os.path.join(self.download_folder, route) for route in all_route_paths])

        self.routes_data = list(results)
        
        execution_time = time.time() - start_time
        print(f"Processed all routes in {execution_time:.2f} seconds with {num_threads} threads.")

        return self.routes_data


    
        
    def getAllStops(self):
        """Returns all stops from all route timetables using parallel processing."""
        all_routes_data = self.getAllRoutesData()  # Fetch all routes data efficiently


        def extract_stops(route):
            stops = [] # Using a set to avoid duplicate stops
            for day, stops_list in route.items():
                if day == 'route':
                    continue
                for stop_data in stops_list:
                    stops.append(stop_data)
            return stops

        with ThreadPoolExecutor() as executor:
            results = executor.map(extract_stops, all_routes_data)

        # Flatten the results into a list
        all_stops = [stop for stops in results for stop in stops]

        return all_stops

    def hasStop(self, stop_to_search):
        """Checks if a stop exists in the timetable data."""
        all_stops = self.getAllStops()
        return any(stop_to_search.lower() == stop['stop'].lower() for stop in all_stops)

    def findRoutesFor(self, stop, dest):
        """Finds routes that include both the stop and destination using parallel processing."""
        all_routes_data = self.getAllRoutesData()  # Ensure data is fetched correctly

        stop_lower = stop.lower()
        dest_lower = dest.lower()

        def route_matches(route):
            for day in ['MONDAYS TO FRIDAYS', 'SATURDAYS']:
                if day in route:
                    stops_set = {stop_data['stop'].lower() for stop_data in route[day]}  # Convert list to set
                    if stop_lower in stops_set and dest_lower in stops_set:
                        return route
            return None

        with ThreadPoolExecutor() as executor:
            results = executor.map(route_matches, all_routes_data)

        return [route for route in results if route is not None]


# Example usage:
if __name__ == "__main__":
    timetable_extractor = TimetableExtractor()
    route_code = 'D02'  # Example route code
    print(timetable_extractor.findRoutesFor("Turf Club","Montague Gardens"))
