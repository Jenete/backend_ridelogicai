import os
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
from pdf_service import PDFService, PlaceMapService
from schedule_service import ScheduleService
from nlp_test import extract_possible_routes, score_routes_by_query_match, generate_suggestions


pdf_service = PDFService()
place_service = PlaceMapService()
app = Flask(__name__)
CORS(app)


@app.route('/files', methods=['GET'])
def list_files():
    return jsonify({'files': pdf_service.fetch_pdf_links()})

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    return send_from_directory(pdf_service.download_folder, filename, as_attachment=True)

@app.route('/files/list', methods=['GET'])
def list_all_files():
    return jsonify({'files': pdf_service.list_downloaded_pdfs()})

@app.route('/download-all', methods=['GET'])
def download_all():
    files = pdf_service.download_pdfs()
    return jsonify({'status': 'Download complete', 'files': files})

@app.route('/extract/<filename>', methods=['GET'])
def extract_from_pdf(filename):
    places = place_service.extract_text_from_pdf(filename)
    return jsonify({'places': places, 'placesMap': place_service.places_map})

@app.route('/schedules', methods=['GET'])
def get_schedule():
    schedule_service = ScheduleService()
    # Get user location and destination from query parameters
    user_location = request.args.get('user_location')
    dest = request.args.get('destination')

    if not user_location or not dest:
        return jsonify({"error": "Missing user_location or destination"}), 400

    # Call the method to get times for the given locations
    times = schedule_service.find_times_for_location_and_destination(user_location, dest)
    
    # If times were found, return them in the response, otherwise, return a message
    if times:
        return jsonify({"times": times}), 200
    else:
        return jsonify({"message": f"No schedule found for {user_location} to {dest}."}), 404

# Create an endpoint to get all places
@app.route('/places', methods=['GET'])
def get_all_places():
    schedule_service = ScheduleService()
    places = schedule_service.get_all_places()

    if places:
        return jsonify({"places": places})
    else:
        return jsonify({"message": "No places available."}), 404
    
@app.route("/interpret", methods=["POST"])
def interpret():
    data = request.get_json()
    query = data.get("query", "")

    if not query:
        return jsonify({"error": "Missing 'query' in request."}), 400

    options = extract_possible_routes(query)
    print("\nHere are some interpretations of your request:")

    sorted_options = score_routes_by_query_match(query,options)
    

    interpretations = generate_suggestions(sorted_options)
    print(interpretations)

    return jsonify({
        "query": query,
        "interpretations": interpretations,
        "options": sorted_options
    })

if __name__ == '__main__':
    app.run(debug=True)

