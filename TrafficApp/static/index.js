async function predictTraffic() {
    let origin = document.getElementById("origin").value;
    let destination = document.getElementById("destination").value;
    let day = document.getElementById("pred_day").value;
    let time = document.getElementById("pred_time").value;

    if (!origin.trim() || !destination.trim()) {
        alert("Please enter both origin and destination");
        return;
    }

    let statusMsg = `Checking traffic from ${origin} to ${destination}`;
    if (day !== "now") statusMsg += ` for ${day}`;
    if (time) statusMsg += ` at ${time}`;
    displayMessage(`${statusMsg}...`, "user");

    let response = await fetch("/predict/", {
        method: "POST",
        headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRFToken": getCookie("csrftoken")
        },
        body: new URLSearchParams({ origin, destination, day, time })
    });

    let data = await response.json();
    console.log("Backend response:", data);

    if (data.error) {
        displayMessage(`Error: ${data.error}`, "bot");
        return;
    }

    let botReply = `
🚗 **${data.is_prediction ? "Future Prediction" : "Route Analysis"} Complete**\n

📍 **Route:** ${data.route}\n
${data.is_prediction ? "" : `📏 **Distance:** ${data.distance} km\n`}
${data.is_prediction ? "" : `🚀 **Avg Speed:** ${data.speed} km/h\n`}
⏰ **Hour:** ${data.hour}:00\n
🗓 **Day:** ${data.day}\n
🚦 **Congestion:** ${data.congestion}\n
${data.is_prediction ? `🎯 **Confidence:** ${data.confidence}%\n` : ""}
⏳ **Estimated Travel Time:** ${data.travel_time}${data.is_prediction ? "" : " mins"}\n

${data.is_prediction ? "*Based on historical AI patterns.*" : "*Data has been saved for future intelligence.*"}
`;

    displayMessage(botReply, "bot");
}




function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
        let cookies = document.cookie.split(";");
        for (let cookie of cookies) {
            cookie = cookie.trim();
            if (cookie.startsWith(name + "=")) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function displayMessage(msg, sender) {
    let chatBox = document.getElementById("chatbox");

    let bubble;

    if (sender === "user") {
        bubble = `
        <div class="flex justify-end">
            <div class="bg-gray-200 p-4 rounded-xl max-w-[70%]">
                ${msg}
            </div>
        </div>`;
    } else {
        bubble = `
        <div class="flex justify-start">
            <div class="bg-blue-600 text-white p-4 rounded-xl max-w-[70%]">
                ${msg}
            </div>
        </div>`;
    }

    chatBox.innerHTML += bubble;
    chatBox.scrollTop = chatBox.scrollHeight;
}

// document.getElementById("message") is no longer in dashboard.html
// if (document.getElementById("message")) { ... }


function getCSRFToken() {
    return document.cookie
        .split("; ")
        .find(row => row.startsWith("csrftoken"))
        ?.split("=")[1];
}


// ── Audio Recording ──────────────────────────────────────────
let mediaRecorder = null;
let audioChunks   = [];
let isRecording   = false;
 
const micBtn = document.querySelector('[data-icon="mic"]');
 
if (micBtn) {
    micBtn.addEventListener("click", () => {
        if (!isRecording) {
            startRecording();
        } else {
            stopRecording();
        }
    });
}
 
async function startRecording() {
    try {
        // Request microphone access from the browser
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
 
        audioChunks = [];
        mediaRecorder = new MediaRecorder(stream);
 
        // Collect audio data as it comes in
        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };
 
        // When recording stops, send audio to Django
        mediaRecorder.onstop = async () => {
            const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
            await sendAudioToDjango(audioBlob);
 
            // Stop all microphone tracks to release mic
            stream.getTracks().forEach(track => track.stop());
        };
 
        mediaRecorder.start();
        isRecording = true;
 
        // Visual feedback — show the button is recording
        micBtn.style.color = "red";
        micBtn.title = "Click to stop recording";
 
    } catch (err) {
        alert("Microphone access denied. Please allow microphone access.");
        console.error("Mic error:", err);
    }
}
 
function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
    }
    isRecording = false;
    micBtn.style.color = "";
    micBtn.title = "Click to start recording";
}
 
async function sendAudioToDjango(audioBlob) {
    // Show a temporary "transcribing..." message
    displayMessage("🎙 Transcribing your voice...", "bot");
 
    const formData = new FormData();
    formData.append("audio", audioBlob, "recording.webm");
 
    try {
        const response = await fetch("/transcribe/", {
            method: "POST",
            headers: { "X-CSRFToken": getCookie("csrftoken") },
            body: formData
        });
 
        const data = await response.json();
 
        if (data.error) {
            displayMessage("Could not understand audio. Please try again.", "bot");
            return;
        }
 
        // Put the transcribed text into the chat input
        const input = document.getElementById("message");
        input.value = data.text;
 
        // Automatically send it as a message
        displayMessage(`You said: "${data.text}"`, "user");
        await sendMessage();
 
    } catch (err) {
        console.error("Audio send error:", err);
        displayMessage("Audio upload failed. Please type instead.", "bot");
    }
}

// View password

const passwordInput = document.getElementById("password");
const togglePassword = document.getElementById("togglePassword");
const icon = togglePassword.querySelector("span");

togglePassword.addEventListener("click", () => {
    const isPassword = passwordInput.type === "password";

    // Toggle input type
    passwordInput.type = isPassword ? "text" : "password";

    // Toggle icon text (Material Icons)
    icon.textContent = isPassword ? "visibility_off" : "visibility";

    // Optional: update data-icon attribute
    icon.setAttribute("data-icon", isPassword ? "visibility_off" : "visibility");
});

function initAutocomplete() {
    // Bias results towards Buea, Cameroon
    const buea = new google.maps.LatLng(4.1522, 9.2314);
    const options = {
        componentRestrictions: { country: "cm" },
        fields: ["address_components", "geometry", "name", "formatted_address"],
        location: buea,
        radius: 10000, // 10km radius for biasing
        strictBounds: false
    };

    // Initialize for Origin
    const originInput = document.getElementById('origin');
    if (originInput) {
        new google.maps.places.Autocomplete(originInput, options);
    }

    // Initialize for Destination
    const destInput = document.getElementById('destination');
    if (destInput) {
        new google.maps.places.Autocomplete(destInput, options);
    }
}

    // Run the initialization
google.maps.event.addDomListener(window, 'load', initAutocomplete);

// ── Alerts System ──────────────────────────────────────────
async function fetchAlerts() {
    try {
        const response = await fetch("/alerts/");
        const data = await response.json();
        const alertsList = document.getElementById("alerts-list");

        if (data.alerts && data.alerts.length > 0) {
            alertsList.innerHTML = data.alerts.map(alert => `
                <div class="p-3 bg-error-container/20 border-l-4 border-error rounded-r-xl">
                    <p class="text-xs font-bold text-on-error-container">${alert.route}</p>
                    <p class="text-[10px] text-error font-semibold">Gridlock: ${alert.travel_time} mins</p>
                    <p class="text-[9px] text-on-surface-variant/60 mt-1">${alert.timestamp}</p>
                </div>
            `).join("");
        } else {
            alertsList.innerHTML = `<p class="text-xs text-green-600 font-medium">All clear! No gridlocks detected in Buea.</p>`;
        }
    } catch (err) {
        console.error("Alerts error:", err);
    }
}

// Fetch alerts every 2 minutes
setInterval(fetchAlerts, 120000);
// Initial fetch
fetchAlerts();