let currentThreadId = null;

async function predictTraffic() {
    let origin = document.getElementById("origin").value;
    let destination = document.getElementById("destination").value;
    let day = document.getElementById("pred_day").value;
    let time = document.getElementById("pred_time").value;

    if (!origin.trim() || !destination.trim()) {
        alert("Please enter both origin and destination");
        return;
    }

    if (window.UI) window.UI.startProgress();

    try {
        let statusMsg = `
            <div class="flex items-center gap-2 text-white">
                <span class="material-symbols-outlined text-sm animate-spin">sync</span>
                <span>Checking traffic from <span class="font-bold">${origin}</span> to <span class="font-bold">${destination}</span>${day !== "now" ? ` for <span class="font-bold">${day}</span>` : ""}${time ? ` at <span class="font-bold">${time}</span>` : ""}...</span>
            </div>
        `;
        displayMessage(statusMsg, "user");

        let bodyParams = { origin, destination, day, time };
        if (currentThreadId) {
            bodyParams.thread_id = currentThreadId;
        }

        let response = await fetch("/predict/", {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
                "X-CSRFToken": getCookie("csrftoken")
            },
            body: new URLSearchParams(bodyParams)
        });

        let data = await response.json();
        console.log("Backend response:", data);

        if (data.error) {
            displayMessage(`
                <div class="flex items-center gap-3 text-error">
                    <span class="material-symbols-outlined">error</span>
                    <p class="font-bold">Error: ${data.error}</p>
                </div>
            `, "bot");
            return;
        }

    if (data.thread_id) {
        if (!currentThreadId) {
            currentThreadId = data.thread_id;
            loadChatThreads(); // Refresh history list to show the new thread
        }
    }

    let interpretation = "";
    let suggestion = "";
    let statusEmoji = "";
    let headerColor = "";

    if (data.congestion === 'Low') {
        interpretation = "You're good to go! The roads are looking clear.";
        suggestion = "It's a great time to start your journey. Drive safely!";
        statusEmoji = "🟢";
        headerColor = "text-green-700";
    } else if (data.congestion === 'Medium') {
        interpretation = "Expect some light traffic.";
        suggestion = "It's not too bad, but maybe leave a few minutes earlier just to be safe!";
        if (data.recommended_departure) {
            suggestion += `<br><br><span class="inline-flex items-center gap-1.5 px-2 py-1 bg-blue-50 text-blue-700 rounded-lg border border-blue-200 mt-2">
                <span class="material-symbols-outlined text-sm">schedule</span>
                <b>Tip:</b> If you can, leave at <b>${data.recommended_departure.time}</b> for <b>${data.recommended_departure.congestion}</b> traffic (${data.recommended_departure.travel_time} mins).
            </span>`;
        }
        statusEmoji = "🟡";
        headerColor = "text-yellow-700";
    } else {
        interpretation = "Expect delays! Heavy traffic detected.";
        suggestion = "Consider waiting a bit or taking an alternative route if possible.";
        if (data.recommended_departure) {
            suggestion += `<br><br><span class="inline-flex items-center gap-1.5 px-2 py-1 bg-green-50 text-green-700 rounded-lg border border-green-200 mt-2">
                <span class="material-symbols-outlined text-sm">schedule</span>
                <b>Tip:</b> A better time to leave is <b>${data.recommended_departure.time}</b> (${data.recommended_departure.travel_time} mins, <b>${data.recommended_departure.congestion}</b> traffic).
            </span>`;
        }
            statusEmoji = "🔴";
            headerColor = "text-red-700";
        }

        let botReply = `
        <div class="flex flex-col gap-6 w-full font-sans text-on-surface">
            <!-- Header Section with Badge -->
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                    <div class="p-2 bg-primary/10 rounded-lg">
                        <span class="material-symbols-outlined text-primary">${data.is_prediction ? "auto_graph" : "on_device_training"}</span>
                    </div>
                    <div>
                        <h3 class="font-headline font-bold text-lg leading-none">${data.is_prediction ? "Smart Forecast" : "Live Traffic Update"}</h3>
                        <p class="text-xs text-on-surface-variant">${new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})} • Verified Source</p>
                    </div>
                </div>
                <div class="flex items-center gap-1.5 px-3 py-1 rounded-full ${data.congestion === 'Low' ? 'bg-green-100 text-green-700' : data.congestion === 'Medium' ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'} border border-current/20">
                    <span class="w-2 h-2 rounded-full bg-current animate-pulse"></span>
                    <span class="text-xs font-bold uppercase tracking-wider">${data.congestion} Traffic</span>
                </div>
            </div>

            <!-- Summary Card -->
            <div class="bg-white rounded-3xl p-6 border border-outline-variant/30 shadow-xl shadow-primary/5">
                <p class="text-sm text-on-surface-variant mb-6">
                    I've analyzed the route from <span class="text-on-surface font-semibold underline decoration-primary/20">${origin}</span> to <span class="text-on-surface font-semibold underline decoration-primary/20">${destination}</span>. 
                    ${data.is_prediction ? `Forecast for <b>${data.day}</b> at <b>${data.hour}:00</b>:` : "Current status:"}
                </p>

                <!-- Key Metrics Grid -->
                <div class="grid grid-cols-2 gap-4 mb-6">
                    <div class="bg-surface-container-low p-4 rounded-2xl border border-outline-variant/10">
                        <p class="text-[10px] uppercase tracking-widest text-on-surface-variant font-bold mb-1">Travel Time</p>
                        <div class="flex items-baseline gap-1">
                            <span class="text-3xl font-black text-primary">${data.travel_time}</span>
                            <span class="text-sm font-bold text-primary/60">mins</span>
                        </div>
                    </div>
                    <div class="bg-surface-container-low p-4 rounded-2xl border border-outline-variant/10">
                        <p class="text-[10px] uppercase tracking-widest text-on-surface-variant font-bold mb-1">Distance</p>
                        <div class="flex items-baseline gap-1">
                            <span class="text-3xl font-black text-on-surface">${data.distance}</span>
                            <span class="text-sm font-bold text-on-surface-variant">km</span>
                        </div>
                    </div>
                </div>

                <!-- Status Interpretation -->
                <div class="flex items-start gap-4 p-4 rounded-2xl ${data.congestion === 'Low' ? 'bg-green-50' : data.congestion === 'Medium' ? 'bg-yellow-50' : 'bg-red-50'} mb-6">
                    <span class="text-3xl">${statusEmoji}</span>
                    <div>
                        <p class="font-bold text-on-surface leading-tight mb-1">${interpretation}</p>
                        <p class="text-sm text-on-surface-variant leading-relaxed">${suggestion}</p>
                    </div>
                </div>

                <!-- Technical Details Accordion-like list -->
                <div class="space-y-3 pt-4 border-t border-outline-variant/20">
                    <div class="flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <span class="material-symbols-outlined text-sm text-on-surface-variant">speed</span>
                            <span class="text-xs font-medium text-on-surface-variant">Average Speed</span>
                        </div>
                        <span class="text-xs font-bold text-on-surface">${data.speed} km/h</span>
                    </div>
                    <div class="flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <span class="material-symbols-outlined text-sm text-on-surface-variant">history</span>
                            <span class="text-xs font-medium text-on-surface-variant">Normal Duration</span>
                        </div>
                        <span class="text-xs font-bold text-on-surface">${data.normal_duration} mins</span>
                    </div>
                    <div class="flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <span class="material-symbols-outlined text-sm text-on-surface-variant">verified</span>
                            <span class="text-xs font-medium text-on-surface-variant">Confidence Score</span>
                        </div>
                        <div class="flex items-center gap-1">
                            <span class="text-xs font-bold text-primary">High</span>
                            <div class="flex gap-0.5">
                                <div class="w-1 h-3 rounded-full bg-primary"></div>
                                <div class="w-1 h-3 rounded-full bg-primary"></div>
                                <div class="w-1 h-3 rounded-full bg-primary"></div>
                                <div class="w-1 h-3 rounded-full bg-primary/20"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
    `;

    if (data.segments_delay && data.segments_delay.length > 0) {
        let delayMsg = `
            <div class="mt-2 space-y-2">
                <p class="text-xs font-bold text-error flex items-center gap-1 uppercase tracking-wider px-1">
                    <span class="material-symbols-outlined text-sm">warning</span> Segment Specific Alerts
                </p>
        `;
        data.segments_delay.forEach(seg => {
            delayMsg += `
                    <div class="p-4 bg-red-50 border-l-4 border-error rounded-r-xl flex items-start gap-3">
                        <span class="material-symbols-outlined text-error text-lg mt-0.5">report_problem</span>
                        <p class="text-xs text-on-surface leading-relaxed">
                            A little delay of <span class="font-bold text-error">${seg.delay} minutes</span> might be encountered at <span class="font-bold underline decoration-error/30">${seg.point}</span>.
                        </p>
                    </div>
            `;
        });
        delayMsg += `</div>`;
        botReply += delayMsg;
    }

    botReply += `</div>`;

        displayMessage(botReply, "bot");
    } catch (err) {
        console.error("Prediction error:", err);
        displayMessage(`
            <div class="flex items-center gap-3 text-error">
                <span class="material-symbols-outlined">error</span>
                <p class="font-bold">Error: ${err.message || 'Failed to get prediction'}</p>
            </div>
        `, "bot");
    } finally {
        if (window.UI) window.UI.stopProgress();
        if (window.TraffikLoader) {
            window.TraffikLoader.hide();
            const predictBtn = document.querySelector('button[onclick="predictTraffic()"]');
            if (predictBtn) window.TraffikLoader.revertButton(predictBtn);
        }
    }
}

async function loadChatThreads() {
    const historyList = document.getElementById("history-list");
    if (!historyList) return;

    // Show skeletons while loading
    const skeletonTemplate = document.getElementById('skeleton-table-row-template');
    if (skeletonTemplate) {
        // Create 3 skeleton rows
        let skeletonHtml = '';
        for(let i=0; i<3; i++) {
            skeletonHtml += `
                <div class="flex items-center gap-3 px-4 py-3 animate-pulse">
                    <div class="w-8 h-8 bg-slate-200 rounded-lg skeleton"></div>
                    <div class="flex-1 space-y-2">
                        <div class="h-3 bg-slate-200 rounded w-3/4 skeleton"></div>
                        <div class="h-2 bg-slate-100 rounded w-1/2 skeleton"></div>
                    </div>
                </div>
            `;
        }
        historyList.innerHTML = skeletonHtml;
    }

    try {
        const response = await fetch("/chat-history/");
        const data = await response.json();

        if (data.history && data.history.length > 0) {
            historyList.innerHTML = data.history.map(thread => `
                <div onclick="loadThread('${thread.id}')" 
                     class="group flex items-center gap-3 px-4 py-3 rounded-lg cursor-pointer transition-all hover:bg-slate-200 dark:hover:bg-slate-800 ${currentThreadId === thread.id ? 'bg-slate-200 dark:bg-slate-800' : ''} content-fade-in">
                    <span class="material-symbols-outlined text-lg text-slate-400 group-hover:text-primary transition-colors">chat_bubble</span>
                    <div class="flex-1 min-w-0">
                        <p class="text-xs font-semibold text-slate-700 dark:text-slate-300 truncate">${thread.title}</p>
                        <p class="text-[10px] text-slate-400">${thread.timestamp}</p>
                    </div>
                </div>
            `).join("");
        } else {
            historyList.innerHTML = `<p class="px-4 py-2 text-[10px] text-slate-500 italic">No history yet</p>`;
        }
    } catch (err) {
        console.error("Error loading chat threads:", err);
    }
}

async function loadThread(threadId) {
    currentThreadId = threadId;
    document.getElementById("chatbox").innerHTML = "";
    
    // Update active state in sidebar
    loadChatThreads();

    try {
        const response = await fetch(`/chat-history/${threadId}/`);
        const data = await response.json();

        if (data.messages) {
            data.messages.forEach(item => {
                displayMessage(item.message, "user");
                let botReply = constructBotReply(item.response, item.timestamp);
                displayMessage(botReply, "bot");
            });
        }
    } catch (err) {
        console.error("Error loading thread:", err);
    }
}

function startNewAnalysis() {
    currentThreadId = null;
    document.getElementById("chatbox").innerHTML = "";
    document.getElementById("origin").value = "";
    document.getElementById("destination").value = "";
    document.getElementById("pred_time").value = "";
    document.getElementById("pred_day").value = "now";
    
    // Update sidebar UI
    loadChatThreads();
    
    displayMessage("New analysis started. Where would you like to go?", "bot");
}

function constructBotReply(trafficData, timestamp) {
    let interpretation = "";
    let suggestion = "";
    let statusEmoji = "";
    
    if (trafficData.congestion === 'Low') {
        interpretation = "You're good to go! The roads are looking clear.";
        suggestion = "It's a great time to start your journey. Drive safely!";
        statusEmoji = "🟢";
    } else if (trafficData.congestion === 'Medium') {
        interpretation = "Expect some light traffic.";
        suggestion = "It's not too bad, but maybe leave a few minutes earlier just to be safe!";
        if (trafficData.recommended_departure) {
            suggestion += `<br><br><span class="inline-flex items-center gap-1.5 px-2 py-1 bg-blue-50 text-blue-700 rounded-lg border border-blue-200 mt-2">
                <span class="material-symbols-outlined text-sm">schedule</span>
                <b>Tip:</b> If you can, leave at <b>${trafficData.recommended_departure.time}</b> for <b>${trafficData.recommended_departure.congestion}</b> traffic (${trafficData.recommended_departure.travel_time} mins).
            </span>`;
        }
        statusEmoji = "🟡";
    } else {
        interpretation = "Expect delays! Heavy traffic detected.";
        suggestion = "Consider waiting a bit or taking an alternative route if possible.";
        if (trafficData.recommended_departure) {
            suggestion += `<br><br><span class="inline-flex items-center gap-1.5 px-2 py-1 bg-green-50 text-green-700 rounded-lg border border-green-200 mt-2">
                <span class="material-symbols-outlined text-sm">schedule</span>
                <b>Tip:</b> A better time to leave is <b>${trafficData.recommended_departure.time}</b> (${trafficData.recommended_departure.travel_time} mins, <b>${trafficData.recommended_departure.congestion}</b> traffic).
            </span>`;
        }
        statusEmoji = "🔴";
    }

    let botReply = `
        <div class="flex flex-col gap-6 w-full font-sans text-on-surface">
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                    <div class="p-2 bg-primary/10 rounded-lg">
                        <span class="material-symbols-outlined text-primary">${trafficData.is_prediction ? "auto_graph" : "on_device_training"}</span>
                    </div>
                    <div>
                        <h3 class="font-headline font-bold text-lg leading-none">${trafficData.is_prediction ? "Smart Forecast" : "Live Traffic Update"}</h3>
                        <p class="text-xs text-on-surface-variant">${timestamp || 'Verified Source'}</p>
                    </div>
                </div>
                <div class="flex items-center gap-1.5 px-3 py-1 rounded-full ${trafficData.congestion === 'Low' ? 'bg-green-100 text-green-700' : trafficData.congestion === 'Medium' ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'} border border-current/20">
                    <span class="w-2 h-2 rounded-full bg-current"></span>
                    <span class="text-xs font-bold uppercase tracking-wider">${trafficData.congestion} Traffic</span>
                </div>
            </div>

            <div class="bg-white rounded-3xl p-6 border border-outline-variant/30 shadow-xl shadow-primary/5">
                <p class="text-sm text-on-surface-variant mb-6">
                    I analyzed the route from <span class="text-on-surface font-semibold underline decoration-primary/20">${trafficData.route.split('-')[0]}</span> to <span class="text-on-surface font-semibold underline decoration-primary/20">${trafficData.route.split('-')[1]}</span>.
                    ${trafficData.is_prediction ? `Forecast for <b>${trafficData.day}</b> at <b>${trafficData.hour}:00</b>:` : "Status at that time:"}
                </p>

                <div class="grid grid-cols-2 gap-4 mb-6">
                    <div class="bg-surface-container-low p-4 rounded-2xl border border-outline-variant/10">
                        <p class="text-[10px] uppercase tracking-widest text-on-surface-variant font-bold mb-1">Travel Time</p>
                        <div class="flex items-baseline gap-1">
                            <span class="text-3xl font-black text-primary">${trafficData.travel_time}</span>
                            <span class="text-sm font-bold text-primary/60">mins</span>
                        </div>
                    </div>
                    <div class="bg-surface-container-low p-4 rounded-2xl border border-outline-variant/10">
                        <p class="text-[10px] uppercase tracking-widest text-on-surface-variant font-bold mb-1">Distance</p>
                        <div class="flex items-baseline gap-1">
                            <span class="text-3xl font-black text-on-surface">${trafficData.distance}</span>
                            <span class="text-sm font-bold text-on-surface-variant">km</span>
                        </div>
                    </div>
                </div>

                <div class="flex items-start gap-4 p-4 rounded-2xl ${trafficData.congestion === 'Low' ? 'bg-green-50' : trafficData.congestion === 'Medium' ? 'bg-yellow-50' : 'bg-red-50'}">
                    <span class="text-3xl">${statusEmoji}</span>
                    <div>
                        <p class="font-bold text-on-surface leading-tight mb-1">${interpretation}</p>
                        <p class="text-sm text-on-surface-variant leading-relaxed">${suggestion}</p>
                    </div>
                </div>
            </div>
        </div>
    `;
    return botReply;
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
        <div class="flex justify-end content-fade-in">
            <div class="bg-primary-container text-on-primary-container p-4 rounded-2xl rounded-tr-none shadow-sm max-w-[85%] md:max-w-[70%]">
                <p class="text-sm font-medium">${msg}</p>
            </div>
        </div>`;
    } else {
        bubble = `
        <div class="flex justify-start content-fade-in">
            <div class="bg-white border border-outline-variant/20 p-5 rounded-2xl rounded-tl-none shadow-md w-full max-w-[95%] md:max-w-[85%] text-on-surface">
                ${msg}
            </div>
        </div>`;
    }

    chatBox.insertAdjacentHTML('beforeend', bubble);
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
        const input = document.getElementById("origin");
        if (input) {
            input.value = data.text;
            displayMessage(`You said: "${data.text}"`, "user");
        }
 
    } catch (err) {
        console.error("Audio send error:", err);
        displayMessage("Audio upload failed. Please type instead.", "bot");
    }
}

// View password
const passwordInput = document.getElementById("password");
const togglePassword = document.getElementById("togglePassword");

if (passwordInput && togglePassword) {
    const icon = togglePassword.querySelector("span");
    togglePassword.addEventListener("click", () => {
        const isPassword = passwordInput.type === "password";
        passwordInput.type = isPassword ? "text" : "password";
        icon.textContent = isPassword ? "visibility_off" : "visibility";
        icon.setAttribute("data-icon", isPassword ? "visibility_off" : "visibility");
    });
}

function initAutocomplete() {
    if (typeof google === 'undefined' || !google.maps || !google.maps.places) {
        console.error("Google Maps API not loaded");
        return;
    }
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
if (typeof google !== 'undefined' && google.maps && google.maps.event) {
    google.maps.event.addDomListener(window, 'load', initAutocomplete);
} else {
    // If API script is not yet loaded, it will be handled by the callback in the URL
    window.addEventListener('load', initAutocomplete);
}

// ── Alerts System ──────────────────────────────────────────
async function fetchAlerts() {
    const alertsList = document.getElementById("alerts-list");
    if (!alertsList) return;

    // Show skeleton while loading if list is empty
    if (alertsList.innerHTML.trim() === '' || alertsList.querySelector('p')) {
        const skeletonCard = document.getElementById('skeleton-card-template');
        if (skeletonCard) {
            alertsList.innerHTML = skeletonCard.innerHTML;
        }
    }

    try {
        const response = await fetch("/alerts/");
        const data = await response.json();

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
loadChatThreads();