let currentThreadId = null;

function createNode(tag, className = "", text = null) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== null && text !== undefined) element.textContent = String(text);
    return element;
}

function appendText(parent, tag, className, text) {
    const child = createNode(tag, className, text);
    parent.appendChild(child);
    return child;
}

function buildTrafficReply(data, timestamp, origin, destination) {
    const congestion = ["Low", "Medium", "High"].includes(data.congestion)
        ? data.congestion : "Unknown";
    const tone = congestion === "Low" ? "green" : congestion === "Medium" ? "yellow" : "red";
    const panel = createNode("div", "flex flex-col gap-6 w-full font-sans text-on-surface");
    const header = createNode("div", "flex items-center justify-between");
    const identity = createNode("div", "flex items-center gap-2");
    const iconBox = createNode("div", "p-2 bg-primary/10 rounded-lg");
    appendText(iconBox, "span", "material-symbols-outlined text-primary",
        data.is_prediction ? "auto_graph" : "on_device_training");
    identity.appendChild(iconBox);
    const heading = createNode("div");
    appendText(heading, "h3", "font-headline font-bold text-lg leading-none",
        data.is_prediction ? "Smart Forecast" : "Live Traffic Update");
    appendText(heading, "p", "text-xs text-on-surface-variant", timestamp || "Verified Source");
    identity.appendChild(heading);
    const badge = createNode("div", `flex items-center gap-1.5 px-3 py-1 rounded-full bg-${tone}-100 text-${tone}-700 border border-current/20`);
    appendText(badge, "span", "w-2 h-2 rounded-full bg-current animate-pulse", "");
    appendText(badge, "span", "text-xs font-bold uppercase tracking-wider", `${congestion} Traffic`);
    header.append(identity, badge);
    panel.appendChild(header);

    const card = createNode("div", "bg-white rounded-3xl p-6 border border-outline-variant/30 shadow-xl shadow-primary/5");
    const routeText = createNode("p", "text-sm text-on-surface-variant mb-6");
    routeText.append("I've analyzed the route from ");
    appendText(routeText, "span", "text-on-surface font-semibold underline decoration-primary/20", origin);
    routeText.append(" to ");
    appendText(routeText, "span", "text-on-surface font-semibold underline decoration-primary/20", destination);
    routeText.append(". ");
    if (data.is_prediction) routeText.append(`Forecast for ${data.day || "the selected day"} at ${data.hour ?? "—"}:00.`);
    else routeText.append("Current status.");
    card.appendChild(routeText);

    const metrics = createNode("div", "grid grid-cols-2 gap-4 mb-6");
    const addMetric = (label, value, unit, classes) => {
        const box = createNode("div", "bg-surface-container-low p-4 rounded-2xl border border-outline-variant/10");
        appendText(box, "p", "text-[10px] uppercase tracking-widest text-on-surface-variant font-bold mb-1", label);
        const line = createNode("div", "flex items-baseline gap-1");
        appendText(line, "span", classes, value ?? "N/A");
        appendText(line, "span", "text-sm font-bold text-primary/60", unit);
        box.appendChild(line);
        metrics.appendChild(box);
    };
    addMetric("Travel Time", data.travel_time, "mins", "text-3xl font-black text-primary");
    addMetric("Distance", data.distance, "km", "text-3xl font-black text-on-surface");
    card.appendChild(metrics);

    const summary = createNode("div", `flex items-start gap-4 p-4 rounded-2xl bg-${tone}-50 mb-6`);
    appendText(summary, "span", "text-3xl", congestion === "Low" ? "🟢" : congestion === "Medium" ? "🟡" : "🔴");
    const interpretation = createNode("div");
    const expectation = congestion === "Low" ? "You're good to go! The roads are looking clear."
        : congestion === "Medium" ? "Expect some light traffic."
        : "Expect delays! Heavy traffic detected.";
    appendText(interpretation, "p", "font-bold text-on-surface leading-tight mb-1", expectation);
    appendText(interpretation, "p", "text-sm text-on-surface-variant leading-relaxed",
        congestion === "Low" ? "It's a great time to start your journey. Drive safely!"
            : congestion === "Medium" ? "It's not too bad, but maybe leave a few minutes earlier just to be safe!"
            : "Consider waiting a bit or taking an alternative route if possible.");
    if (data.recommended_departure) {
        const departure = data.recommended_departure;
        const tip = createNode("p", "inline-flex items-center gap-1.5 px-2 py-1 bg-blue-50 text-blue-700 rounded-lg border border-blue-200 mt-2");
        appendText(tip, "span", "material-symbols-outlined text-sm", "schedule");
        const tipText = createNode("span");
        tipText.append("Tip: Leave at ");
        appendText(tipText, "b", "", departure.time);
        tipText.append(` for ${departure.congestion} traffic (${departure.travel_time} mins).`);
        tip.appendChild(tipText);
        interpretation.appendChild(tip);
    }
    summary.appendChild(interpretation);
    card.appendChild(summary);

    const makeRow = (label, value) => {
        const row = createNode("div", "flex items-center justify-between");
        appendText(row, "span", "text-xs font-medium text-on-surface-variant", label);
        appendText(row, "span", "text-xs font-bold text-on-surface", value ?? "N/A");
        return row;
    };
    const details = createNode("div", "space-y-3 pt-4 border-t border-outline-variant/20");
    details.append(
        makeRow("Average Speed", data.speed == null ? "N/A" : `${data.speed} km/h`),
        makeRow("Normal Duration", data.normal_duration == null ? "N/A" : `${data.normal_duration} mins`),
        makeRow("ML Confidence", data.confidence_score == null ? "N/A" : `${data.confidence_score}%`)
    );
    card.appendChild(details);

    const comparison = createNode("div", "mt-6 pt-6 border-t border-outline-variant/20");
    appendText(comparison, "h4", "text-[10px] uppercase tracking-widest text-on-surface-variant font-bold mb-4", "Hybrid AI Analysis");
    comparison.append(
        makeRow("Google Maps ETA", data.google_traffic_duration == null ? "N/A" : `${data.google_traffic_duration} mins`),
        makeRow("AI Adjustment", data.ai_adjustment == null ? "N/A" : `${data.ai_adjustment > 0 ? "+" : ""}${data.ai_adjustment} mins`)
    );
    if (Array.isArray(data.adjustment_reasons) && data.adjustment_reasons.length) {
        const reasons = createNode("ul", "px-3 space-y-1");
        data.adjustment_reasons.forEach(reason => appendText(reasons, "li", "text-[11px] text-on-surface-variant", reason));
        comparison.appendChild(reasons);
    }
    comparison.appendChild(
        makeRow("Final Smart ETA", data.final_smart_eta == null ? "N/A" : `${data.final_smart_eta} mins`)
    );
    card.appendChild(comparison);

    const risk = data.risk_analysis || { level: "Low", stability: "Stable" };
    const context = data.context_analysis || { weather: "N/A", school_rush: "No", office_rush: "No" };
    const contextPanel = createNode("div", "mt-6 pt-6 border-t border-outline-variant/20 grid grid-cols-2 gap-4");
    const pressure = typeof data.traffic_pressure_score === "number" ? data.traffic_pressure_score : 0;
    const pressureBox = createNode("div");
    appendText(pressureBox, "h4", "text-[10px] uppercase tracking-widest text-on-surface-variant font-bold mb-2", "Pressure Score");
    appendText(pressureBox, "p", "text-xs font-bold", `${pressure}/100 · ${data.pressure_level || "Unknown"} Pressure Environment`);
    contextPanel.appendChild(pressureBox);
    const riskBox = createNode("div");
    appendText(riskBox, "h4", "text-[10px] uppercase tracking-widest text-on-surface-variant font-bold mb-2", "Route Risk");
    appendText(riskBox, "p", "text-xs font-bold", `${risk.level || "Unknown"} Risk · Stability: ${risk.stability || "Unknown"}`);
    contextPanel.appendChild(riskBox);
    card.appendChild(contextPanel);

    const contextGrid = createNode("div", "mt-6 pt-6 border-t border-outline-variant/20 grid grid-cols-3 gap-2");
    [["Weather", context.weather], ["School", context.school_rush === "Yes" ? "Rush Hour" : "No Rush"], ["Office", context.office_rush === "Yes" ? "Rush Hour" : "No Rush"]]
        .forEach(([label, value]) => {
            const item = createNode("div", "p-2 bg-surface-container-lowest rounded-xl border border-outline-variant/10 flex flex-col items-center text-center");
            appendText(item, "span", "text-[9px] text-on-surface-variant uppercase font-bold", label);
            appendText(item, "span", "text-[10px] font-bold", value);
            contextGrid.appendChild(item);
        });
    card.appendChild(contextGrid);

    if (Array.isArray(data.ai_reasoning) && data.ai_reasoning.length) {
        const reasoning = createNode("div", "mt-6 p-4 bg-surface-container-high rounded-2xl border border-outline-variant/20");
        appendText(reasoning, "h4", "text-xs font-bold text-on-surface mb-3", "Why this prediction?");
        const list = createNode("div", "grid grid-cols-1 gap-2");
        data.ai_reasoning.forEach(reason => appendText(list, "p", "text-xs text-on-surface-variant", reason));
        reasoning.appendChild(list);
        card.appendChild(reasoning);
    }
    panel.appendChild(card);

    if (Array.isArray(data.segments_delay) && data.segments_delay.length) {
        const segments = createNode("div", "mt-2 space-y-2");
        appendText(segments, "p", "text-xs font-bold text-error uppercase tracking-wider px-1", "Segment Specific Alerts");
        data.segments_delay.forEach(segment => {
            const item = createNode("div", "p-4 bg-red-50 border-l-4 border-error rounded-r-xl");
            const text = createNode("p", "text-xs text-on-surface leading-relaxed");
            text.append("A little delay of ");
            appendText(text, "span", "font-bold text-error", `${segment.delay} minutes`);
            text.append(" might be encountered at ");
            appendText(text, "span", "font-bold underline decoration-error/30", segment.point);
            text.append(".");
            item.appendChild(text);
            segments.appendChild(item);
        });
        panel.appendChild(segments);
    }
    return panel;
}

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
        const status = createNode("div", "flex items-center gap-2 text-white");
        appendText(status, "span", "material-symbols-outlined text-sm animate-spin", "sync");
        const statusText = createNode("span");
        statusText.append("Checking traffic from ");
        appendText(statusText, "b", "font-bold", origin);
        statusText.append(" to ");
        appendText(statusText, "b", "font-bold", destination);
        if (day !== "now") statusText.append(` for ${day}`);
        if (time) statusText.append(` at ${time}`);
        statusText.append("...");
        status.appendChild(statusText);
        displayMessage(status, "user");

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

        if (data.error) {
            const error = createNode("div", "flex items-center gap-3 text-error");
            appendText(error, "span", "material-symbols-outlined", "error");
            appendText(error, "p", "font-bold", `Error: ${data.error}`);
            displayMessage(error, "bot");
            return;
        }

        // Keep the guest trial counter in sync after a free prediction.
        if (typeof data.remaining_free === "number") {
            const remEl = document.getElementById("guest-remaining");
            if (remEl) remEl.textContent = data.remaining_free;
        }

        // Guest trial exhausted → show the "create an account" wall.
        if (data.auth_required) {
            const wall = createNode("div", "p-5 bg-primary/5 border border-primary/20 rounded-xl text-center space-y-3");
            appendText(wall, "span", "material-symbols-outlined text-primary text-4xl", "lock");
            appendText(wall, "p", "font-bold text-on-surface", data.message);
            const links = createNode("div", "flex items-center justify-center gap-3 pt-1");
            const signup = appendText(links, "a", "bg-primary text-white font-bold px-5 py-2.5 rounded-lg hover:bg-primary-container transition-colors", "Create free account");
            signup.href = "/signup/";
            const signin = appendText(links, "a", "text-primary font-semibold hover:underline", "Sign in");
            signin.href = "/login/";
            wall.appendChild(links);
            displayMessage(wall, "bot");
            return;
        }

    if (data.thread_id) {
        if (!currentThreadId) {
            currentThreadId = data.thread_id;
            loadChatThreads(); // Refresh history list to show the new thread
        }
    }

        const timestamp = new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"}) + " • Verified Source";
        displayMessage(buildTrafficReply(data, timestamp, origin, destination), "bot");
    } catch (err) {
        console.error("Prediction error:", err);
        const error = createNode("div", "flex items-center gap-3 text-error");
        appendText(error, "span", "material-symbols-outlined", "error");
        appendText(error, "p", "font-bold", `Error: ${err.message || "Failed to get prediction"}`);
        displayMessage(error, "bot");
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
    // Guests have no saved history and the endpoint is login-only; skip quietly.
    if (window.IS_AUTHENTICATED === false) return;

    const historyList = document.getElementById("history-list");
    if (!historyList) return;

    // Build loading placeholders as nodes; history content is stored user data.
    const skeletons = [];
    for (let i = 0; i < 3; i++) {
        const row = createNode("div", "flex items-center gap-3 px-4 py-3 animate-pulse");
        appendText(row, "div", "w-8 h-8 bg-slate-200 rounded-lg skeleton", "");
        const lines = createNode("div", "flex-1 space-y-2");
        appendText(lines, "div", "h-3 bg-slate-200 rounded w-3/4 skeleton", "");
        appendText(lines, "div", "h-2 bg-slate-100 rounded w-1/2 skeleton", "");
        row.appendChild(lines);
        skeletons.push(row);
    }
    historyList.replaceChildren(...skeletons);

    try {
        const response = await fetch("/chat-history/");
        const data = await response.json();

        if (data.history && data.history.length > 0) {
            const rows = data.history.map(thread => {
                const row = createNode("div", `group flex items-center gap-3 px-4 py-3 rounded-lg cursor-pointer transition-all hover:bg-slate-200 dark:hover:bg-slate-800 ${currentThreadId === thread.id ? "bg-slate-200 dark:bg-slate-800" : ""} content-fade-in`);
                row.setAttribute("role", "button");
                row.tabIndex = 0;
                row.addEventListener("click", () => loadThread(thread.id));
                row.addEventListener("keydown", event => {
                    if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        loadThread(thread.id);
                    }
                });
                appendText(row, "span", "material-symbols-outlined text-lg text-slate-400 group-hover:text-primary transition-colors", "chat_bubble");
                const details = createNode("div", "flex-1 min-w-0");
                appendText(details, "p", "text-xs font-semibold text-slate-700 dark:text-slate-300 truncate", thread.title);
                appendText(details, "p", "text-[10px] text-slate-400", thread.timestamp);
                row.appendChild(details);
                return row;
            });
            historyList.replaceChildren(...rows);
        } else {
            historyList.replaceChildren(appendText(createNode("p"), "span", "px-4 py-2 text-[10px] text-slate-500 italic", "No history yet"));
        }
    } catch (err) {
        console.error("Error loading chat threads:", err);
    }
}

async function loadThread(threadId) {
    currentThreadId = threadId;
    document.getElementById("chatbox").replaceChildren();

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
    document.getElementById("chatbox").replaceChildren();
    document.getElementById("origin").value = "";
    document.getElementById("destination").value = "";
    document.getElementById("pred_time").value = "";
    document.getElementById("pred_day").value = "now";

    // Update sidebar UI
    loadChatThreads();

    displayMessage("New analysis started. Where would you like to go?", "bot");
}

function constructBotReply(trafficData, timestamp) {
    const origin = trafficData.departure || (trafficData.route ? trafficData.route.split("-")[0] : "Origin");
    const destination = trafficData.destination || (trafficData.route ? trafficData.route.split("-")[1] : "Destination");
    return buildTrafficReply(trafficData, timestamp || "Verified Source", origin, destination);
}

function displayMessage(message, sender) {
    const chatBox = document.getElementById("chatbox");
    const wrapper = createNode("div", sender === "user"
        ? "flex justify-end content-fade-in"
        : "flex justify-start content-fade-in");
    const bubble = createNode("div", sender === "user"
        ? "bg-primary-container text-on-primary-container p-4 rounded-2xl rounded-tr-none shadow-sm max-w-[85%] md:max-w-[70%]"
        : "bg-white border border-outline-variant/20 p-5 rounded-2xl rounded-tl-none shadow-md w-full max-w-[95%] md:max-w-[85%] text-on-surface");
    if (message instanceof Node) {
        bubble.appendChild(message);
    } else {
        appendText(bubble, "p", sender === "user" ? "text-sm font-medium" : "", message);
    }
    wrapper.appendChild(bubble);
    chatBox.appendChild(wrapper);
    chatBox.scrollTop = chatBox.scrollHeight;
}

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

// Voice input is intentionally disabled: there is no /transcribe/ backend
// endpoint, so the previous recording flow always failed with a 404. The mic
// button now shows a friendly notice instead of attempting a broken upload.
if (micBtn) {
    micBtn.title = "Voice input coming soon";
    micBtn.addEventListener("click", () => {
        if (typeof displayMessage === "function") {
            displayMessage("🎙 Voice input isn't available yet — please type your route.", "bot");
        }
    });
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

    // Legacy Places Autocomplete is unavailable to new Google projects (since
    // Mar 2025). Wrap construction so an unavailable/blocked Places API degrades
    // gracefully to plain text inputs instead of throwing — predictions use the
    // typed text regardless.
    try {
        const originInput = document.getElementById('origin');
        if (originInput) new google.maps.places.Autocomplete(originInput, options);

        const destInput = document.getElementById('destination');
        if (destInput) new google.maps.places.Autocomplete(destInput, options);
    } catch (e) {
        console.warn("Address autocomplete unavailable; manual entry still works.", e);
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
// The gridlock-alerts feature is not enabled: there is no /alerts/ endpoint
// (it's commented out in urls.py), so the previous 2-minute poll only produced
// 404s. Polling removed until the backend endpoint is implemented.

loadChatThreads();
