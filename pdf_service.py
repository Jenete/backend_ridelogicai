import os
import re
import requests
from bs4 import BeautifulSoup
import PyPDF2
import fitz  # PyMuPDF
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed


class PDFService:
    def __init__(self, download_folder='pdf_downloads'):
        self.url = 'https://www.gabs.co.za/Timetable.aspx'
        self.file_url = 'https://www.gabs.co.za'
        self.download_folder = download_folder
        os.makedirs(self.download_folder, exist_ok=True)

    def fetch_pdf_links(self):
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(self.url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        buttons = soup.find_all('button', {'title': 'Download'}, onclick=True)
        pdf_urls = []
        for button in buttons:
            pdf_match = re.search(r"window\.open\(['\"](.*?)['\"]", button['onclick'])
            if pdf_match:
                pdf_url = pdf_match.group(1)
                if not pdf_url.startswith('http'):
                    pdf_url = f"{self.file_url}/{pdf_url.lstrip('/')}"
                pdf_urls.append(pdf_url)
        return pdf_urls
    
    def fetch_pdf_links_with_param(self, letter = 'A'):
        session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0'
        }

        # Step 1: Initial GET to extract hidden form fields
        response = session.get(self.url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')

        def get_field(name):
            field = soup.find('input', {'name': name})
            return field['value'] if field else ''

        viewstate = get_field('__VIEWSTATE')
        viewstategenerator = get_field('__VIEWSTATEGENERATOR')
        eventvalidation = get_field('__EVENTVALIDATION')  # optional but often required

        # Step 2: POST to simulate clicking the control with __EVENTTARGET='M'
        payload = {
            '__EVENTTARGET': letter,
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': viewstate,
            '__VIEWSTATEGENERATOR': viewstategenerator,
            '__EVENTVALIDATION': eventvalidation,
        }

        post_response = session.post(self.url, data=payload, headers=headers)
        post_soup = BeautifulSoup(post_response.text, 'html.parser')

        # Step 3: Extract PDF links from the onclick JS
        buttons = post_soup.find_all('button', {'title': 'Download'}, onclick=True)
        pdf_urls = []

        for button in buttons:
            pdf_match = re.search(r"window\.open\(['\"](.*?)['\"]", button['onclick'])
            if pdf_match:
                pdf_url = pdf_match.group(1)
                if not pdf_url.startswith('http'):
                    pdf_url = f"{self.file_url}/{pdf_url.lstrip('/')}"
                pdf_urls.append(pdf_url)

        return pdf_urls
    


    def download_pdfs(self):
        letters = list("ABCDEFHKLMNOPRSTUVW")

        def download_pdf(url):
            try:
                pdf_name = url.split('/')[-1]
                pdf_path = os.path.join(self.download_folder, pdf_name)
                response = requests.get(url, stream=True)
                if response.status_code == 200:
                    with open(pdf_path, 'wb') as pdf_file:
                        for chunk in response.iter_content(chunk_size=1024):
                            pdf_file.write(chunk)
                    return pdf_path
            except Exception as e:
                print(f"Failed to download {url}: {e}")
            return None

        all_urls = []

        # Collect all PDF URLs
        for letter in letters:
            urls = self.fetch_pdf_links_with_param(letter=letter)
            all_urls.extend(urls)

        # Download in parallel
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_url = {executor.submit(download_pdf, url): url for url in all_urls}

            for future in as_completed(future_to_url):
                result = future.result()
                if result:
                    print(f"Downloaded: {result}")
                else:
                    print(f"Failed: {future_to_url[future]}")

        return all_urls

    def list_downloaded_pdfs(self):
        return [f for f in os.listdir(self.download_folder) if os.path.isfile(os.path.join(self.download_folder, f))]

class PlaceMapService:
    def __init__(self):
        self.places_map = []
        self.lock = threading.Lock()

    def add_place(self, place):
        with self.lock:
            existing_place = next((p for p in self.places_map if p['name'] == place['name']), None)
            if existing_place:
                existing_place['times'] = list(set(existing_place['times'] + place['times']))
            else:
                self.places_map.append(place)

    def extract_day_from_text(self, text):
        days = [
            "MONDAYS TO FRIDAYS", "Saturday", "Sunday"
        ]
        daysMap = {
            "MONDAYS TO FRIDAYS":'wd', "Saturday":'wsa', "Sunday":'wsu'
        }
        text_to_ignore = "a  - Mondays,Tuesdays,Wednesdays,Thursdays"
        
        # Make text lowercase for case-insensitive matching
        text_lower = text.lower()
        if text_lower == text_to_ignore:
            return None
        for day in days:
            if re.search(rf'\b{day.lower()}\b', text_lower):
               daysMap[day]  # Return in title case even if matched in lowercase
        for day in days:
            if day.lower() in text_lower:
                return daysMap[day]  # Return in title case even if matched in lowercase

        return None
    
    def flag_times(self, times, flag):
        return [time + flag for time in times]

    def process_text_chunk(self, text, places_found):
        rows = text.split('\n')
        day_flag = 'w'
        prev = ''
        for row in rows:
            is_day = self.extract_day_from_text(row)
            if is_day: #adds a flag to the time
                day_flag = is_day
            inbetweens = row.split('|')
            
            for i, value in enumerate(inbetweens):
                value = value.strip()
                if self.is_place(value):
                    times_flagged= self.flag_times(inbetweens[i + 1:i + 23], day_flag)
                    place = {
                        'name': value,
                        'times': times_flagged,
                        'next': inbetweens[i + 24] if i + 24 < len(inbetweens) else None,
                        'prev': prev
                    }
                    self.add_place(place)
                    with self.lock:
                        if value not in places_found:
                            prev = value
                            places_found.append(value)

    def extract_text_from_pdf(self, pdf_path):
        places_found = []
        pdf_path = os.path.join('pdf_downloads', pdf_path)
        
        with fitz.open(pdf_path) as doc:
            threads = []
            for page in doc:
                text = page.get_text("text") + '\n'
                thread = threading.Thread(target=self.process_text_chunk, args=(text, places_found))
                thread.start()
                threads.append(thread)
            
            for thread in threads:
                thread.join()
        
        return places_found

    def is_place(self, text):
        return not (':' in text or 'via' in text or '-' in text or text.strip() == '')
    

# print('Initializing download')
# pdf_service = PDFService()
# pdf_service.download_pdfs()
# print('Download complete!')

