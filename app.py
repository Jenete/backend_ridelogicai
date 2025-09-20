from flask import Flask, jsonify, send_from_directory, request, abort
from flask_cors import CORS
from pdf_service import PDFService, PlaceMapService
from schedule_service import ScheduleService
from chat_service import ChatService
from nlp_test import extract_possible_routes, score_routes_by_query_match, generate_suggestions, match_locations_sort
import os
from dotenv import load_dotenv
from datetime import datetime
import os

load_dotenv()  # take environment variables from .env.

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


pdf_service = PDFService()
place_service = PlaceMapService()
# Init ChatService with API key
chat_service = ChatService(OPENAI_API_KEY)
if not OPENAI_API_KEY:
    raise ValueError("⚠️ OPENAI_API_KEY is not set in environment variables.")

print("API key loaded:", OPENAI_API_KEY[:5] + "...")
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

# Configure the directory where your timetables are stored
PDF_DIR = os.path.join(os.getcwd(), "pdf_downloads")

@app.route('/file/<path:filename>', methods=['GET'])
def get_file(filename):
    try:
        # Make sure the file exists
        if not os.path.isfile(os.path.join(PDF_DIR, filename)):
            abort(404, description="File not found")

        # Return file (inline or as download depending on headers)
        return send_from_directory(
            directory=PDF_DIR,
            path=filename,
            as_attachment=False,   # set to True if you want to force download
            mimetype="application/pdf"
        )
    except Exception as e:
        abort(500, description=str(e))


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
    
# Create an endpoint to get all places
@app.route('/placesMap', methods=['GET'])
def get_all_placesMap():
    schedule_service = ScheduleService()
    places = {}

    if places:
        return jsonify({"places": places})
    else:
        return jsonify({"message": "No places available."}), 404
    
# Create an endpoint to get all routes
@app.route('/all_routes', methods=['GET'])
def get_all_Routes():
    schedule_service = ScheduleService()
    places = {}
    places = schedule_service.get_files_list_onsite()
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

@app.route("/match-location", methods=["POST"])
def match_location():
    data = request.get_json()
    query = data.get("query", "")

    if not query:
        return jsonify({"error": "Missing 'query' in request."}), 400

    sorted_options = match_locations_sort(query)

    return jsonify({
        "query": query,
        "options": sorted_options
    })

@app.route("/best-times", methods=["POST"])
def best_times():
    try:
        data = request.json
        pdf_files = data.get("pdf_files")  # list of file paths
        time = data.get("time")
        whereto = data.get("whereto")
        from_where = data.get("fromWhere")

        if not all([pdf_files, time, whereto, from_where]):
            missing_fields = "Missing required fields: "
            if not pdf_files:
                missing_fields += "pdf_files "
            if not time:
                missing_fields += "time "
            if not whereto:
                missing_fields += "whereto "
            if not from_where:
                missing_fields += "fromWhere "

            return jsonify({"error": missing_fields}), 400

        result = chat_service.get_best_times_from_timetable(
            pdf_files, time, whereto, from_where
        )
        return jsonify({"result": result})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/ask-text", methods=["POST"])
def ask_text():
    try:
        data = request.json
        prompt = data.get("prompt")
        history = data.get("history", [])

        if not prompt:
            return jsonify({"error": "Missing required field: prompt"}), 400

        result = chat_service.ask_gpt_from_text(prompt, history)
        return jsonify({"response": result})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

# temporary in-memory store
crowd_reports = []

@app.route("/crowd-report", methods=["POST"])
def crowd_report():
    try:
        data = request.json
        report = {
            "routeId": data.get("routeId"),
            "stop": data.get("stop"),
            "status": data.get("status"),
            "userId": data.get("userId", "anon"),
            "timestamp": datetime.utcnow().isoformat(),
            "location": data.get("location"),  # { lat, lng, accuracy }
        }
        crowd_reports.append(report)  # 👉 replace with DB insert later
        return jsonify({"success": True, "report": report}), 201
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/crowd-reports", methods=["GET"])
def get_crowd_reports():
    try:
        route_id = request.args.get("routeId")
        stop = request.args.get("stop")

        # filter results
        results = crowd_reports
        if route_id:
            results = [r for r in results if r["routeId"] == route_id]
        if stop:
            results = [r for r in results if r["stop"].lower() == stop.lower()]

        return jsonify({"success": True, "reports": results}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))  # Render sets PORT env var
    app.run(host="0.0.0.0", port=port)

    


