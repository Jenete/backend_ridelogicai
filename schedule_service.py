import re
import os
from flask import jsonify
from pdf_service import PDFService, PlaceMapService
import concurrent.futures

class Route:
    def __init__(self, from_route, to_route, pdf, effective_date, time_table_no):
        self.from_route = from_route
        self.to_route = to_route
        self.pdf = pdf
        self.effective_date = effective_date
        self.time_table_no = time_table_no
        self.places = []
        self.places_map = {}

    def __str__(self):
        return f"Route({self.from_route} <-> {self.to_route}, Effective Date: {self.effective_date}, Time Table No: {self.time_table_no})"

    def add_places(self, places):
        self.places = places

    def add_places_map(self, places_map):
        self.places_map = places_map

    def getRouteName(self):
        return f"{self.from_route} <-> {self.to_route}"

    def hasPlace(self, placeName):
        return placeName.upper() in self.places

    def getPlaceTimes(self, placeName):
        if self.hasPlace(placeName):
            # Find the place in places_map by name and return its times
            for place in self.places_map:
                if place.get('name') == placeName:
                    return place.get('times', [])
        return []
    
    def getPlaceDetails(self, placeName):
        if self.hasPlace(placeName):
            # Find the place in places_map by name and return its times
            for place in self.places_map:
                if place.get('name') == placeName:
                    return place
        return None


    def getCurrentPlaceAndDestinationRoute(self, placeName, dest, routes):
        if not self.hasPlace(placeName):
            return None

        # Find route with destination
        destination_route = next((route for route in routes if route.to_route == dest), None)
        if destination_route:
            # Check if the current route has the place and destination route exists
            return destination_route if destination_route.hasPlace(placeName) else None
        return None

    def getCurrentPlaceAndDestinationRouteTimes(self, placeName, dest, routes):
        route = self.getCurrentPlaceAndDestinationRoute(placeName, dest, routes)
        if route:
            return route.getPlaceTimes(placeName)
        return []


class ScheduleService:
    def __init__(self):
        self.base_url = "https://scrapper-rsro.onrender.com"
        self.pdf_service = PDFService()
        self.place_service = PlaceMapService()

    # Function to clean up the route data from the file name
    def clean_route_data(self, file_name):
        match = re.match(r"([^_]+(?:_[^_]+)*)___([^_]+(?:_[^_]+)*)_from_(\d+)_to_(\d+)_([\d]+)\.pdf", file_name)
        if match:
            from_route = match.group(1).replace('_', ' ').title()
            to_route = match.group(2).replace('_', ' ').title()
            effective_date = match.group(3)
            time_table_no = match.group(5)
            print('clean data available')
            return Route(from_route, to_route, file_name, effective_date, time_table_no)
        # print(file_name)
        return None

    # Function to fetch the list of files
    def get_files_list(self):
        response = self.pdf_service.list_downloaded_pdfs()
        if response:
            return {'files': response}
        return []
    
    # # Function to fetch the list of files
    # def get_files_list_onsite(self):
    #     response = self.pdf_service.fetch_pdf_links_with_param()
    #     if response:
    #         return {'files': response}
    #     return []

    # Function to extract route data from the PDF file
    def extract_route_data(self, pdf_name):
        # print('extracting route data')
        places = self.place_service.extract_text_from_pdf(pdf_name)
        return {'places': places, 'placesMap': self.place_service.places_map}

    # Function to get the routes, process file data, and extract additional details using threading
    def get_routes(self):
        files = self.get_files_list()['files']
        routes = []
        extracted_data_list = []

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_route = {}

            for file in files:
                route = self.clean_route_data(file)
                if route:
                    # Submit the extraction task to the thread pool
                    future = executor.submit(self.extract_route_data, route.pdf)
                    future_to_route[future] = route
                    routes.append(route)

            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_route):
                route = future_to_route[future]
                try:
                    extracted_data = future.result()
                    if extracted_data:
                        route.add_places(extracted_data['places'])
                        route.add_places_map(extracted_data['placesMap'])
                except Exception as e:
                    print(f"Error processing {route.pdf}: {e}")

        print(f'found {len(routes)} routes')
        return routes
    
    # Method to find times for user location and destination
    def find_times_for_location_and_destination(self, user_location, dest):
        routes = self.get_routes()
        times = []

        # Loop through all routes and fetch times for the user location and destination
        for route in routes:
            # Check if the current route has the user location and destination
            if route.hasPlace(user_location) and route.hasPlace(dest):
                print(f'route: {route}')
                # Get times for the user location
                place_data = route.getPlaceDetails(user_location)
                if place_data == None:
                    continue
                
                times_for_user = place_data.get('times')
                prev_location = place_data.get('prev')
                
                if times_for_user:
                    bus_details = f"Bus {route.getRouteName()} will arrive in {user_location} at: {', '.join(times_for_user)}"
                    timeObject = {'times': times_for_user, 'user_location':user_location, 'destination': dest,'bus_route': route.getRouteName(), 'details':bus_details, 'prev':prev_location}
                    times.append(timeObject)

        # Output the times found
        if times:
            return times
        else:
            response = f"No schedule found for {user_location} to {dest}."
            print(response)
            return response

    def clean_places(self, places):
        invalid_patterns = [
            r"^.*\b(STANDARD|SATURDAYS|SUNDAYS|OPERATED|REG|CONDITIONS|CARRIAGE|WEBSITE|LIABLE|ANY|LOSS|INCONVENIENCE|FAILURE|MAINTAIN|VEHICLES|TIMETABLE).*", # Regex for common invalid phrases
            r"^[A-Za-z]+\.[A-Za-z]+$",  # Abbreviations like A.D.E.
            r"^[A-Za-z]+\s*[A-Za-z]+$", # Single word place names (Optional if you want to keep these)
            r"\(",  # If you want to remove places with parenthesis (like "MAMRE (PARADISE RD)")
            r"^\s*$",  # Remove empty strings
        ]

        valid_places = []
        
        for place in places:
            is_valid = True
            for pattern in invalid_patterns:
                if re.match(pattern, place):
                    is_valid = False
                    break
            
            if is_valid:
                valid_places.append(place)

        return valid_places

    # Method to get all available places
    def get_all_places(self):
        all_places = set()  # Using a set to avoid duplicates
        routes = self.get_routes()  #  method to fetch routes

        for route in routes:
            all_places.update(route.places)  # Add places from each route

        return sorted(all_places)
    
     # Method to get all available places
    def get_all_placesMap(self):
        all_places = []  # Using a set to avoid duplicates
        routes = self.get_routes()  #  method to fetch routes
        
        for route in routes:
            print(route)
            print(route.pdf)
            # # print('\n')
            print(route.places)
            # print(route)
            print('\n')

            all_places.extend(route.places_map)  # Add places from each route

        return all_places
    

    

# # Example usage:

# userlocation = "DU NOON"
# dest = "MAMRE (PARADISE RD)"

# # Example usage:
# schedule_service = ScheduleService()

# schedule_service.get_all_placesMap()

# # Call the method with user location and destination
# schedule_service.find_times_for_location_and_destination(userlocation, dest)