import re
import spacy
from rapidfuzz import process, fuzz

# Load SpaCy model
nlp = spacy.load("en_core_web_sm")

# List of valid locations
VALID_LOCATIONS = [
    "Khayelitsha", "Cape Town", "Bellville", "Mitchells Plain", 
    "Claremont", "Woodstock", "Wynberg", "Table View", "Mowbray",
    "Makhaza", "Harare","Site C", "MAITLAND","ELITHA PARK"
]

# Common fixes for speech-to-text issues
COMMON_FIXES = {
    "fom": "from",
    "frm": "from",
    "khyelistha": "khayelitsha",
    "cpt": "cape town",
    "capetown": "cape town",
    "michels plain": "mitchells plain"
}

# Normalize time words
TIME_KEYWORDS = {
    "morning": "before 12 pm",
    "afternoon": "12 pm to 6 pm",
    "evening": "after 6 pm",
    "noon": "12 pm",
    "night": "after 7 pm"
}

ALIAS_MAP = {
    "Khayelitsha": "SITE C, SITE B, MAKHAZA, HARARE",
    "kasi": "Khayelitsha",
    "mowbray train station": "Mowbray",
    "chills": "Nyanga",
    "gugs": "Gugulethu",
    "VILLAGE 1 SOUTH": "ELITHA PARK",
    "VILLAGE 3 SOUTH": "HARARE",
    "umrhabulo triangle": "MAKHAZA",
}

def preprocess_query(query):
    query = query.lower()
    for wrong, correct in COMMON_FIXES.items():
        query = re.sub(rf"\b{re.escape(wrong)}\b", correct, query)
    return query

def fuzzy_match_location(text):
    match, score, _ = process.extractOne(text, VALID_LOCATIONS, scorer=fuzz.WRatio)
    if score >= 70:
        return match
    return None

def get_standard_location(input_location): #print(get_standard_location("village 1 south"))  → "ELITHA PARK"
    input_location = input_location.strip().lower()

    # Flatten alias map into (alias, standard) list
    alias_pairs = []
    for standard, aliases in ALIAS_MAP.items():
        alias_list = aliases.split(',') if isinstance(aliases, str) else [aliases]
        alias_list.append(standard)  # include the key itself as an alias
        for alias in alias_list:
            alias_pairs.append((alias.strip().lower(), standard))

    # Extract best match
    all_aliases = [alias for alias, _ in alias_pairs]
    match, score, index = process.extractOne(input_location, all_aliases, scorer=fuzz.WRatio)

    if score >= 80:
        return ALIAS_MAP[alias_pairs[index][1]]  # return the corresponding standard name

    return None  # No confident match

def match_locations_sort(locations):
    if not locations:
        return []

    matches = []

    if isinstance(locations, list):
        for location in locations:
            match, score, _ = process.extractOne(location, VALID_LOCATIONS, scorer=fuzz.WRatio)
            if score >= 70:
                matches.append((match, score))
            else:
                alias_name = get_standard_location(location)
                if alias_name:
                    matches.append((alias_name, 100))
    elif isinstance(locations, str):
        match, score, _ = process.extractOne(locations, VALID_LOCATIONS, scorer=fuzz.WRatio)
        if score >= 70:
            matches.append((match, score))
        else:
                alias_name = get_standard_location(location)
                if alias_name:
                    matches.append((alias_name, 100))

    # Sort by score in descending order
    sorted_matches = sorted(matches, key=lambda x: x[1], reverse=True)
    matches_without_scores = [x[0] for x in sorted_matches]
    return matches_without_scores

def extract_time_keyword(text):
    for keyword, range_time in TIME_KEYWORDS.items():
        if keyword in text:
            return range_time
        
    return None

def extract_possible_routes(user_query):
    user_query = preprocess_query(user_query)
    time_range = extract_time_keyword(user_query)
    if not time_range:
        doc = nlp(user_query.lower())
        for ent in doc.ents:
            if ent.label_ == "TIME":
                time_range = ent.text

    # ✅ Fuzzy match any word or bigram in the input
    words = user_query.split()
    possible_locations = set()

    for i in range(len(words)):
        # Check single word
        single = fuzzy_match_location(words[i])
        if single:
            possible_locations.add(single)

        # Check two-word phrases
        if i + 1 < len(words):
            phrase = f"{words[i]} {words[i+1]}"
            phrase_match = fuzzy_match_location(phrase)
            if phrase_match:
                possible_locations.add(phrase_match)

    possible_locations = list(possible_locations)

    route_options = []

    for i in range(len(possible_locations)):
        for j in range(len(possible_locations)):
            if i != j:
                route_options.append({
                    "from": possible_locations[i],
                    "to": possible_locations[j],
                    "time": time_range or "unspecified"
                })

    return route_options


def generate_suggestions(route_options):
    if not route_options:
        return "Sorry, I couldn't understand your route. Can you please provide more details?"

    suggestions = []
    for i, option in enumerate(route_options):
        from_loc = option[0]["from"]
        to_loc = option[0]["to"]
        time = option[0]["time"]
        suggestion = f"A bus from {from_loc} to {to_loc} at {time}?"
        suggestions.append(suggestion)

    suggestions.append(f"Something else")
    return suggestions

def score_routes_by_query_match(query, route_options):
    scored_routes = []

    for option in route_options:
        from_loc = option["from"]
        to_loc = option["to"]
        time = option["time"]

        # Create a sentence out of the route
        route_sentence = f"bus from {from_loc} to {to_loc} at {time}"
        
        # Fuzzy match it against the original user query
        score = fuzz.token_set_ratio(query.lower(), route_sentence.lower())

        scored_routes.append((option, score))

    # Sort by score (highest first)
    scored_routes.sort(key=lambda x: x[1], reverse=True)

    return scored_routes

# CLI Interaction
if __name__ == "__main__":
    print("Smart Bus Assistant (type 'q' to quit)")
    while True:
        query = input("\nEnter your query:\n")
        if query.lower() == 'q':
            break

        options = extract_possible_routes(query)
        print("\nHere are some interpretations of your request:")

        sorted_options = score_routes_by_query_match(query,options)
        print(generate_suggestions(sorted_options))
