import os
import requests

class ChatService:
    def __init__(self, openai_api_key: str):
        self.api_key = openai_api_key
        self.file_cache = {}  # filename → file_id cache

    def upload_file(self, file_path: str) -> str:
        """Upload timetable PDF to OpenAI if not cached, return file_id."""
        if file_path in self.file_cache:
            return self.file_cache[file_path]
        pdf_path = os.path.join('pdf_downloads', file_path)
        with open(pdf_path, "rb") as f:
            files = {"file": (file_path, f, "application/pdf")}
            data = {"purpose": "assistants"}
            headers = {"Authorization": f"Bearer {self.api_key}"}

            res = requests.post("https://api.openai.com/v1/files",
                                headers=headers, files=files, data=data)

        if res.status_code != 200:
            raise Exception(f"Failed to upload {file_path}: {res.text}")

        uploaded = res.json()
        file_id = uploaded["id"]
        self.file_cache[file_path] = file_id
        return file_id

    def get_best_times_from_timetable(self, pdf_files, time, whereto, from_where):
        """Query GPT with uploaded timetables and return best bus suggestion."""
        if not pdf_files:
            raise ValueError("No timetable files provided.")

        detailed_prompt = f"""
            You are RideLogic Bot, an AI transport assistant for Cape Town (taxis, Golden Arrow, fares, routes, ranks).
            Task: Find the best busses (3max) around this time {time} from {from_where} to {whereto} using the uploaded timetables as truth.
            Respond briefly as a JSON object:
            {{"xhosa_version": "...", "english_version": "...", "afrikaans_version": "...", "best_time": ["..."]}}
            """


        # Upload files if needed
        uploaded_files = [self.upload_file(path) for path in pdf_files]

        # Ask GPT
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": "gpt-4.1-mini",  # file-aware + efficient
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": detailed_prompt},
                        *[{"type": "input_file", "file_id": fid} for fid in uploaded_files],
                    ],
                }
            ],
        }

        res = requests.post("https://api.openai.com/v1/responses",
                            headers=headers, json=body)

        if res.status_code != 200:
            raise Exception(f"Failed to query GPT: {res.text}")

        data = res.json()
        return (
            data.get("output_text")
            or data.get("output", [{}])[0].get("content", [{}])[0].get("text")
            or "No response."
        )
    
    def ask_gpt_from_text(self, prompt: str, history=None) -> str:
        """Ask GPT a text question about Cape Town transport."""
        if history is None:
            history = []

        detailed_prompt = (
            f'You are a helpful AI transport assistant for RideLogic. '
            f'Your name is RideLogic Bot. '
            f'Your task is to understand and answer questions related to Cape Town public transport '
            f'including taxis, bus schedules Golden Arrow), fares, routes, and rank locations. '
            f'Respond to: "{prompt}"'
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        body = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {
                    "role": "system",
                    "content": "You are RideLogic, a helpful assistant that gives real-time, friendly advice about taxi and bus transport in South Africa."
                },
                *history,
                {"role": "user", "content": detailed_prompt},
            ],
        }

        res = requests.post(f"https://api.openai.com/v1/chat/completions", headers=headers, json=body)

        if res.status_code != 200:
            raise Exception(f"Failed to query GPT: {res.text}")

        data = res.json()
        return data["choices"][0]["message"]["content"]
