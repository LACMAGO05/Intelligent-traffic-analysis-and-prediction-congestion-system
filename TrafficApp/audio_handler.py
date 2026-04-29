# How it works:
#   1. Browser records audio using MediaRecorder API
#   2. Sends the audio blob to /transcribe/ endpoint
#   3. Django saves it temporarily, runs Whisper on it
#   4. Returns the transcribed text to the frontend
#   5. Frontend puts the text in the chat input and sends it

import os
import uuid
import whisper
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
 
 
# Load Whisper model once at module level (not per request)
# "base" model is a good balance of speed vs accuracy
# Options: "tiny", "base", "small", "medium", "large"
# For a server with limited RAM use "base" or "tiny"
whisper_model = whisper.load_model("base")
 
@login_required
def transcribe_audio(request):
    """
    Receives an audio file from the browser,
    transcribes it using Whisper, returns the text.
 
    Frontend sends: POST /transcribe/ with audio blob
    Returns: {"text": "Mile 17 monday morning"}
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=400)
 
    audio_file = request.FILES.get("audio")
    if not audio_file:
        return JsonResponse({"error": "No audio file received"}, status=400)
 
    # Save the audio blob temporarily to disk
    # Whisper needs a file path, not a stream
    temp_dir      = os.path.join(settings.BASE_DIR, "temp_audio")
    os.makedirs(temp_dir, exist_ok=True)
    temp_filename = os.path.join(temp_dir, f"{uuid.uuid4()}.webm")
 
    try:
        with open(temp_filename, "wb") as f:
            for chunk in audio_file.chunks():
                f.write(chunk)
 
        # Run Whisper transcription
        result = whisper_model.transcribe(temp_filename)
        text   = result["text"].strip()
 
        return JsonResponse({"text": text})
 
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": f"Transcription failed: {str(e)}"}, status=500)
 
    finally:
        # Always delete the temp file after use
        if os.path.exists(temp_filename):
            os.remove(temp_filename)